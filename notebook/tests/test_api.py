from __future__ import annotations

import hashlib

import pytest
from fake_api import TOKEN, FakeApi

from doctune_nb import __version__
from doctune_nb.api import (
    ApiUnavailable,
    ChecksumMismatch,
    ConflictError,
    DocTuneClient,
    DocTuneError,
    NotebookOutdated,
    TokenError,
    TokenExpired,
    TokenRevoked,
)


def test_config_is_parsed_and_sends_version_and_token(api: FakeApi, client: DocTuneClient) -> None:
    cfg = client.config()
    assert cfg.base_model_id == "unsloth/Qwen3.5-4B"
    assert cfg.train_mode == "lora16"
    assert cfg.hyperparams.lora_r == 8 and cfg.hyperparams.batch_size == 2
    assert cfg.dataset.train_count == 16 and len(cfg.dataset.sha256_train) == 64
    call = api.state.calls("GET", "/jobs/current/config")[0]
    assert call.query["notebook_version"] == [__version__]
    assert call.headers["Authorization"] == f"Bearer {TOKEN}"


def test_outdated_notebook_raises_friendly_error(api: FakeApi, client: DocTuneClient) -> None:
    api.state.min_version = "9.0.0"
    with pytest.raises(NotebookOutdated) as exc:
        client.config()
    assert "outdated" in str(exc.value)
    assert exc.value.status == 426
    assert len(api.state.calls("GET", "/jobs/current/config")) == 1  # 4xx: no retry


@pytest.mark.parametrize(
    ("code", "cls", "hint"),
    [
        ("token_expired", TokenExpired, "Create a new token"),
        ("token_revoked", TokenRevoked, "current token"),
        ("token_invalid", TokenError, "whole token"),
    ],
)
def test_token_errors_are_friendly(api: FakeApi, client: DocTuneClient, code: str, cls: type, hint: str) -> None:
    api.state.inject["/jobs/current/config"] = [(401, {"error": code, "message": "Server says no."})]
    with pytest.raises(cls) as exc:
        client.config()
    assert "Server says no." in str(exc.value) and hint in str(exc.value)
    assert TOKEN not in str(exc.value)


def test_wrong_token_against_server(api: FakeApi) -> None:
    c = DocTuneClient("dtj_wrong", api.url, sleep=lambda s: None)
    with pytest.raises(TokenError, match="isn't valid"):
        c.config()


def test_token_format_checked_locally() -> None:
    with pytest.raises(TokenError, match="dtj_"):
        DocTuneClient("abc", "http://x")
    with pytest.raises(TokenError, match="No job token"):
        DocTuneClient("  ", "http://x")


def test_repr_masks_token() -> None:
    c = DocTuneClient(TOKEN, "http://x")
    assert TOKEN not in repr(c) and TOKEN[8:] not in repr(c)


def test_retries_on_5xx_then_succeeds(api: FakeApi, client: DocTuneClient, sleeps: list[float]) -> None:
    api.state.inject["/jobs/current/heartbeat"] = [(503, {"error": "x", "message": "busy"}), (502, {})]
    out = client.heartbeat(3, 10, 1.5)
    assert out == {"ok": True, "cancel_requested": False}
    assert len(api.state.calls("POST", "/jobs/current/heartbeat")) == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]  # exponential backoff


def test_gives_up_after_retries(api: FakeApi, client: DocTuneClient, sleeps: list[float]) -> None:
    api.state.inject["/jobs/current/heartbeat"] = [(500, {})] * 10
    with pytest.raises(ApiUnavailable):
        client.heartbeat(1, 10)
    assert len(api.state.calls("POST", "/jobs/current/heartbeat")) == 4  # 1 + 3 retries


@pytest.mark.parametrize("status", [400, 404, 409, 422])
def test_never_retries_4xx(api: FakeApi, client: DocTuneClient, sleeps: list[float], status: int) -> None:
    api.state.inject["/jobs/current/start"] = [(status, {"error": "job_ended", "message": "This job has ended."})]
    with pytest.raises(DocTuneError) as exc:
        client.start({"gpu_name": "T4"})
    assert len(api.state.calls("POST", "/jobs/current/start")) == 1
    assert sleeps == []
    if status == 409:
        assert isinstance(exc.value, ConflictError) and exc.value.code == "job_ended"


def test_network_error_is_retried(sleeps: list[float]) -> None:
    c = DocTuneClient(TOKEN, "http://127.0.0.1:9", sleep=sleeps.append, retries=2, timeout_s=0.5)
    with pytest.raises(ApiUnavailable, match="Network problem"):
        c.config()
    assert len(sleeps) == 2


def test_signed_upload_has_no_auth_header_and_correct_sha(api: FakeApi, client: DocTuneClient, tmp_path) -> None:
    data = b"PK" + bytes(range(256)) * 5000
    f = tmp_path / "checkpoint.zip"
    f.write_bytes(data)
    client.upload_checkpoint(f, step=7)
    put = api.state.calls("PUT", "/storage/ckpt/upload.zip")[0]
    assert "Authorization" not in put.headers
    assert put.headers["Content-Type"] == "application/zip"
    assert put.body == data
    complete = api.state.calls("POST", "/jobs/current/checkpoint/complete")[0].json()
    assert complete == {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), "step": 7}
    assert api.state.checkpoint and api.state.checkpoint["step"] == 7
    req = api.state.calls("POST", "/jobs/current/checkpoint/upload-url")[0].json()
    assert req == {"size_bytes": len(data), "step": 7}


def test_artifact_upload_and_finish(api: FakeApi, client: DocTuneClient, tmp_path) -> None:
    with pytest.raises(ConflictError, match="adapter"):
        client.finish({"rouge_l_tuned": 0.5}, {})
    f = tmp_path / "adapter.zip"
    f.write_bytes(b"adapter-bytes")
    client.upload_artifact("adapter_safetensors", f)
    assert api.state.artifacts["adapter_safetensors"]["sha256"] == hashlib.sha256(b"adapter-bytes").hexdigest()
    put = api.state.calls("PUT", "/storage/art/adapter_safetensors")[0]
    assert "Authorization" not in put.headers
    out = client.finish({"rouge_l_tuned": 0.5}, {"drive_path": None})
    assert out["ok"] is True
    body = api.state.calls("POST", "/jobs/current/finish")[-1].json()
    assert body == {"metrics": {"rouge_l_tuned": 0.5}, "exports": {"drive_path": None}}


def test_upload_put_retries_on_5xx(api: FakeApi, client: DocTuneClient, tmp_path, sleeps: list[float]) -> None:
    api.state.inject["/storage/ckpt/upload.zip"] = [(503, {})]
    f = tmp_path / "c.zip"
    f.write_bytes(b"x" * 1000)
    client.upload_checkpoint(f, step=1)
    puts = api.state.calls("PUT", "/storage/ckpt/upload.zip")
    assert len(puts) == 2 and puts[1].body == b"x" * 1000  # file re-read on retry


def test_download_verifies_sha(api: FakeApi, client: DocTuneClient, tmp_path) -> None:
    api.state.storage["blob"] = b"hello world"
    good = hashlib.sha256(b"hello world").hexdigest()
    p = client.download_signed(api.signed("blob", "get"), tmp_path / "a.bin", sha256=good)
    assert p.read_bytes() == b"hello world"
    assert "Authorization" not in api.state.calls("GET", "/storage/blob")[0].headers
    with pytest.raises(ChecksumMismatch):
        client.download_signed(api.signed("blob", "get"), tmp_path / "b.bin", sha256="0" * 64)
    assert not (tmp_path / "b.bin").exists() and not (tmp_path / "b.bin.part").exists()


def test_expired_download_link_is_friendly(api: FakeApi, client: DocTuneClient, tmp_path) -> None:
    with pytest.raises(DocTuneError, match="may have expired"):
        client.download_signed(api.signed("missing", "get"), tmp_path / "x", desc="checkpoint")


def test_pause_fail_training_complete_bodies(api: FakeApi, client: DocTuneClient) -> None:
    client.pause("user_stopped", 12)
    client.fail("boom" * 1000, step=3, fatal=True)
    client.training_complete(10, 0.25, 123.4)
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "user_stopped", "step": 12}
    fail = api.state.calls("POST", "/jobs/current/fail")[0].json()
    assert len(fail["error"]) == 2000 and fail["fatal"] is True and fail["step"] == 3
    assert api.state.calls("POST", "/jobs/current/training-complete")[0].json() == {
        "final_step": 10,
        "final_loss": 0.25,
        "train_runtime_s": 123.4,
    }
