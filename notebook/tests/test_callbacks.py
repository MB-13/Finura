from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fake_api import FakeApi

from doctune_nb import ui
from doctune_nb.api import ChecksumMismatch, DocTuneClient
from doctune_nb.callbacks import (
    META_FILE,
    HeartbeatCallback,
    TimedCheckpointCallback,
    UploadCheckpointCallback,
    unzip_checkpoint,
    zip_checkpoint,
)
from doctune_nb.train import checkpoint_meta, prepare_resume


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def state(step: int, max_steps: int = 100) -> SimpleNamespace:
    return SimpleNamespace(global_step=step, max_steps=max_steps)


def control() -> SimpleNamespace:
    return SimpleNamespace(should_save=False, should_training_stop=False)


def write_checkpoint(root: Path, step: int) -> Path:
    d = root / f"checkpoint-{step}"
    d.mkdir(parents=True)
    for name, data in {
        "adapter_model.safetensors": b"A" * 4096,
        "adapter_config.json": b'{"r": 8}',
        "optimizer.pt": b"O" * 2048,
        "scheduler.pt": b"S",
        "rng_state.pth": b"R",
        "trainer_state.json": json.dumps({"global_step": step}).encode(),
        "training_args.bin": b"T",
    }.items():
        (d / name).write_bytes(data)
    return d


# ------------------------------------------------------------------------------------------- heartbeat


def test_heartbeat_is_time_throttled(api: FakeApi, client: DocTuneClient) -> None:
    clock = Clock()
    hb = HeartbeatCallback(client, 100, every_s=30, clock=clock)
    args, ctl = SimpleNamespace(), control()
    hb.on_train_begin(args, state(0), ctl)  # forced
    for step in range(1, 10):
        clock.t += 5
        hb.on_log(args, state(step), ctl, logs={"loss": 2.0 - step * 0.1, "learning_rate": 1e-4, "epoch": 0.1})
        hb.on_step_end(args, state(step), ctl)
    # t = +45 s over 9 steps -> begin + one at +30 s
    calls = api.state.calls("POST", "/jobs/current/heartbeat")
    assert len(calls) == 2
    body = calls[1].json()
    assert body["step"] == 6 and body["max_steps"] == 100
    assert body["loss"] == pytest.approx(1.4) and body["lr"] == 1e-4 and body["epoch"] == 0.1
    hb.on_train_end(args, state(9), ctl)  # forced
    assert len(api.state.calls("POST", "/jobs/current/heartbeat")) == 3


def test_heartbeat_cancel_stops_training(api: FakeApi, client: DocTuneClient) -> None:
    api.state.cancel_requested = True
    hb = HeartbeatCallback(client, 10, clock=Clock())
    ctl = control()
    hb.on_train_begin(SimpleNamespace(), state(0), ctl)
    assert ctl.should_training_stop is True and hb.cancelled


def test_heartbeat_revoked_token_stops_training(api: FakeApi, client: DocTuneClient) -> None:
    api.state.inject["/jobs/current/heartbeat"] = [(401, {"error": "token_revoked", "message": "revoked"})]
    hb = HeartbeatCallback(client, 10, clock=Clock())
    ctl = control()
    hb.on_train_begin(SimpleNamespace(), state(0), ctl)
    assert ctl.should_training_stop is True


def test_heartbeat_network_failure_never_raises(api: FakeApi, client: DocTuneClient) -> None:
    api.state.inject["/jobs/current/heartbeat"] = [(500, {})] * 10
    hb = HeartbeatCallback(client, 10, clock=Clock())
    ctl = control()
    hb.on_train_begin(SimpleNamespace(), state(0), ctl)
    assert ctl.should_training_stop is False


def test_heartbeat_nan_loss_sent_as_null(api: FakeApi, client: DocTuneClient) -> None:
    hb = HeartbeatCallback(client, 10, clock=Clock())
    hb.on_log(SimpleNamespace(), state(1), control(), logs={"loss": float("nan")})
    assert api.state.calls("POST", "/jobs/current/heartbeat")[0].json()["loss"] is None
    assert hb.nan_steps == 1


def test_callbacks_answer_every_trainer_event() -> None:
    hb = TimedCheckpointCallback(7)
    for ev in ("on_init_end", "on_substep_end", "on_prediction_step", "on_some_future_event"):
        assert getattr(hb, ev)(None, None, None) is None
    with pytest.raises(AttributeError):
        _ = hb.not_an_event


# ------------------------------------------------------------------------------------------- timed save


def test_timed_checkpoint_forces_save_after_interval() -> None:
    clock = Clock()
    cb = TimedCheckpointCallback(7, clock=clock)
    cb.on_train_begin(None, state(0), control())
    ctl = control()
    clock.t += 6 * 60
    cb.on_step_end(None, state(5), ctl)
    assert ctl.should_save is False
    clock.t += 61
    cb.on_step_end(None, state(6), ctl)
    assert ctl.should_save is True
    cb.on_save(None, state(6), ctl)
    ctl2 = control()
    clock.t += 30
    cb.on_step_end(None, state(7), ctl2)
    assert ctl2.should_save is False


def test_timed_checkpoint_not_twice_for_same_step() -> None:
    clock = Clock()
    cb = TimedCheckpointCallback(5, clock=clock)
    cb.on_train_begin(None, state(20), control())  # resumed at 20
    clock.t += 10_000
    ctl = control()
    cb.on_step_end(None, state(20), ctl)
    assert ctl.should_save is False


# ------------------------------------------------------------------------------------------- zip + upload


def test_checkpoint_zip_contains_all_files_stored(tmp_path: Path) -> None:
    ck = write_checkpoint(tmp_path / "ckpt", 20)
    z = zip_checkpoint(ck, tmp_path / "c.zip", {"seed": 1})
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        assert {
            "adapter_model.safetensors",
            "adapter_config.json",
            "optimizer.pt",
            "scheduler.pt",
            "rng_state.pth",
            "trainer_state.json",
            "training_args.bin",
            META_FILE,
        } == names
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
        assert json.loads(zf.read(META_FILE)) == {"seed": 1}


def test_unzip_rejects_path_traversal(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("../evil.txt", "x")
    with pytest.raises(Exception, match="unsafe"):
        unzip_checkpoint(bad, tmp_path / "out")


def test_upload_callback_on_save(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    out = tmp_path / "ckpt"
    write_checkpoint(out, 30)
    cb = UploadCheckpointCallback(client, {"seed": 5}, tmp_path / "up", sleep=lambda s: None)
    cb.on_save(SimpleNamespace(output_dir=str(out)), state(30), control())
    assert cb.uploaded_steps == [30]
    assert api.state.checkpoint and api.state.checkpoint["step"] == 30
    with zipfile.ZipFile(__import__("io").BytesIO(api.state.storage["ckpt/latest.zip"])) as z:
        assert "optimizer.pt" in z.namelist()
        assert json.loads(z.read(META_FILE)) == {"seed": 5, "step": 30}
    assert not (tmp_path / "up" / "checkpoint.zip").exists()  # local zip cleaned up


def test_upload_failure_is_retried_and_never_raises(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    out = tmp_path / "ckpt"
    write_checkpoint(out, 10)
    api.state.inject["/jobs/current/checkpoint/upload-url"] = [(500, {})] * 100
    waits: list[float] = []
    cb = UploadCheckpointCallback(client, {}, tmp_path / "up", attempts=3, sleep=waits.append)
    ctl = control()
    cb.on_save(SimpleNamespace(output_dir=str(out)), state(10), ctl)  # must not raise
    assert cb.failed_steps == [10] and cb.uploaded_steps == []
    assert len(waits) == 2 and ctl.should_training_stop is False
    # next save works again
    api.state.inject.clear()
    write_checkpoint(out, 11)
    cb.on_save(SimpleNamespace(output_dir=str(out)), state(11), ctl)
    assert cb.uploaded_steps == [11]


def test_upload_missing_dir_is_harmless(client: DocTuneClient, tmp_path: Path) -> None:
    cb = UploadCheckpointCallback(client, {}, tmp_path / "up")
    cb.on_save(SimpleNamespace(output_dir=str(tmp_path)), state(3), control())
    assert cb.failed_steps == [3]


# ------------------------------------------------------------------------------------------- resume


def _upload(client: DocTuneClient, tmp_path: Path, step: int, meta: dict) -> None:
    ck = write_checkpoint(tmp_path / "src", step)
    z = zip_checkpoint(ck, tmp_path / "src.zip", meta)
    client.upload_checkpoint(z, step)


def test_resume_downloads_verifies_and_unzips(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    _upload(client, tmp_path, 40, checkpoint_meta(cfg))
    path, step = prepare_resume(client, cfg, tmp_path / "job")
    assert step == 40 and path.name == "checkpoint-40"
    assert (path / "trainer_state.json").exists() and (path / "optimizer.pt").read_bytes() == b"O" * 2048
    assert "Authorization" not in api.state.calls("GET", "/storage/ckpt/latest.zip")[0].headers
    # second call in the same session reuses the local checkpoint (no new download)
    path2, step2 = prepare_resume(client, cfg, tmp_path / "job")
    assert (path2, step2) == (path, 40)
    assert len(api.state.calls("GET", "/storage/ckpt/latest.zip")) == 1


def test_resume_without_checkpoint(client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    assert prepare_resume(client, cfg, tmp_path / "job") == (None, 0)


def test_resume_rejects_corrupted_checkpoint(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    _upload(client, tmp_path, 40, checkpoint_meta(cfg))
    api.state.storage["ckpt/latest.zip"] += b"corrupt"
    with pytest.raises(ChecksumMismatch):
        prepare_resume(client, cfg, tmp_path / "job")


def test_resume_refuses_other_dataset(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    _upload(client, tmp_path, 40, {**checkpoint_meta(cfg), "dataset_sha256_train": "f" * 64})
    with pytest.raises(ui.StopNotebook, match="different dataset"):
        prepare_resume(client, cfg, tmp_path / "job")


def test_resume_prefers_newer_local_checkpoint(api: FakeApi, client: DocTuneClient, tmp_path: Path) -> None:
    cfg = client.config()
    _upload(client, tmp_path, 40, checkpoint_meta(cfg))
    write_checkpoint(tmp_path / "job" / "ckpt", 50)  # upload of 50 failed earlier in this session
    path, step = prepare_resume(client, cfg, tmp_path / "job")
    assert step == 50 and api.state.calls("GET", "/storage/ckpt/latest.zip") == []
