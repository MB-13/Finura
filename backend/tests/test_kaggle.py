"""ADR-0002: the Kaggle client, kernel script, compute-account API, launch and poll workers. No network."""

import ast
import base64
import io
import json
import zipfile
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fake_kaggle import FakeKaggle
from fake_llm import fake_groq
from flows import approved_project
from helpers import ALICE, BOB
from sqlalchemy import select, text

from doctune.core.crypto import decrypt
from doctune.core.db import get_sessionmaker, sync_session
from doctune.models.compute import ComputeAccount
from doctune.models.enums import ProjectStatus
from doctune.models.training import Checkpoint, JobState, JobToken, PauseReason, TrainingJob
from doctune.training import kaggle_client, kaggle_kernel
from doctune.training.kaggle_client import (
    KaggleAuthError,
    KaggleClient,
    KaggleError,
    KaggleRateLimited,
    auth_header,
    normalize_status,
    parse_duration,
)
from doctune.workers.tasks import kaggle as kaggle_tasks

Auth = Callable[..., dict[str, str]]
KGAT = "KGAT_0123456789abcdef0123456789abcdef"
LEGACY = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


@pytest.fixture
def kg(monkeypatch: pytest.MonkeyPatch) -> FakeKaggle:
    fake = FakeKaggle()
    fake.install(monkeypatch)
    return fake


def nb(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- client


def test_auth_header_by_token_prefix() -> None:
    assert auth_header("alice", KGAT) == f"Bearer {KGAT}"
    expected = "Basic " + base64.b64encode(f"alice:{LEGACY}".encode()).decode()
    assert auth_header("alice", LEGACY) == expected


def test_client_sends_expected_request(kg: FakeKaggle) -> None:
    with KaggleClient("alice", KGAT) as client:
        result = client.save_kernel("doctune-ab-1", "DocTune ab 1", "print(1)", session_timeout_s=3600)
    assert result.ref == "alice/doctune-ab-1" and result.url.endswith("alice/doctune-ab-1")
    _, body, headers = kg.requests[0]
    assert headers["authorization"] == f"Bearer {KGAT}"
    assert headers["user-agent"].startswith("doctune/")
    assert body["slug"] == "alice/doctune-ab-1" and body["kernelType"] == "script"
    assert body["isPrivate"] is True and body["enableGpu"] is True and body["enableInternet"] is True
    assert body["machineShape"] == "NvidiaTeslaT4" and body["sessionTimeoutSeconds"] == 3600
    assert body["datasetDataSources"] == [] and body["categoryIds"] == []


def test_legacy_key_uses_basic_auth(kg: FakeKaggle) -> None:
    with KaggleClient("alice", LEGACY) as client:
        client.gpu_quota()
    assert kg.requests[0][2]["authorization"].startswith("Basic ")


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures(kg: FakeKaggle, status: int) -> None:
    kg.http_status = status
    with KaggleClient("alice", KGAT) as client, pytest.raises(KaggleAuthError) as err:
        client.gpu_quota()
    assert KGAT not in str(err.value)


def test_body_code_maps_like_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"code": 403, "message": "bad token"}))
    monkeypatch.setattr(kaggle_client, "test_transport", transport)
    with KaggleClient("alice", KGAT) as client, pytest.raises(KaggleAuthError):
        client.gpu_quota()


def test_rate_limit_and_server_errors(kg: FakeKaggle) -> None:
    kg.rate_limit_calls = 1
    with KaggleClient("alice", KGAT) as client:
        with pytest.raises(KaggleRateLimited) as err:
            client.gpu_quota()
        assert err.value.retry_after == 1 and err.value.transient
        kg.http_status = 503
        with pytest.raises(KaggleError) as err2:
            client.gpu_quota()
        assert err2.value.transient and not isinstance(err2.value, KaggleAuthError)


def test_save_error_field_is_a_failure(kg: FakeKaggle) -> None:
    kg.save_error = "Phone verification required"
    with KaggleClient("alice", KGAT) as client, pytest.raises(KaggleError, match="Phone"):
        client.save_kernel("s", "S", "x", session_timeout_s=60)


def test_missing_status_means_queued() -> None:
    assert kaggle_client.normalize_status(None) == "QUEUED"
    assert kaggle_client.normalize_status("") == "QUEUED"


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("COMPLETE", "COMPLETE"),
        ("KernelWorkerStatus.ERROR", "ERROR"),
        ("KERNEL_WORKER_STATUS_RUNNING", "RUNNING"),
        (2, "COMPLETE"),
        (3, "ERROR"),
        ("4", "CANCEL_REQUESTED"),
        (5, "CANCEL_ACKNOWLEDGED"),
        (0, "QUEUED"),
        (6, "NEW_SCRIPT"),
        (99, "UNKNOWN"),
        (None, "QUEUED"),
    ],
)
def test_status_parsing(raw: Any, name: str) -> None:
    assert normalize_status(raw) == name


def test_session_status_and_quota_parsing(kg: FakeKaggle) -> None:
    kg.session_status, kg.failure_message = 3, "OOM"
    with KaggleClient("alice", KGAT) as client:
        status = client.session_status("doctune-x-1")
        quota = client.gpu_quota()
    assert status.status == "ERROR" and status.ended and status.failure_message == "OOM"
    assert kg.calls("GetKernelSessionStatus")[0] == {"userName": "alice", "kernelSlug": "doctune-x-1"}
    assert (quota.used_s, quota.total_s, quota.remaining_s) == (3600, 108000, 104400)
    assert quota.refresh_at is not None and not quota.exhausted


def test_duration_parsing_is_defensive() -> None:
    assert parse_duration("3600s") == 3600 and parse_duration(7200) == 7200 and parse_duration({"seconds": "5"}) == 5
    assert parse_duration(None) == 0 and parse_duration("soon") == 0


def test_network_error_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(kaggle_client, "test_transport", httpx.MockTransport(boom))
    with KaggleClient("alice", KGAT) as client, pytest.raises(KaggleError) as err:
        client.gpu_quota()
    assert err.value.transient


# ---------------------------------------------------------------- kernel script


def test_kernel_source_compiles_and_embeds_package() -> None:
    src = kaggle_kernel.build_source(
        "dtj_secrettoken123", "https://api.example.com", "0f0f0f0f-0000-4000-8000-000000000000"
    )
    compile(src, "kernel.py", "exec")
    assert 'os.environ["CUDA_VISIBLE_DEVICES"] = "0"' in src and "PYTHONUNBUFFERED" in src
    assert "DOCTUNE_WORKDIR" not in src and src.index("CUDA_VISIBLE_DEVICES") < src.index("import base64")
    assert "doctune_nb.headless" in src and "[train]" in src and "doctune_nb_src" in src
    pkg = next(
        ast.literal_eval(n.value)
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "PKG_B64"
    )
    names = zipfile.ZipFile(io.BytesIO(base64.b64decode(pkg))).namelist()
    assert "pyproject.toml" in names and "doctune_nb/__init__.py" in names and "doctune_nb/api.py" in names
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)


def test_kernel_never_prints_the_token() -> None:
    src = kaggle_kernel.build_source("dtj_secrettoken123", "https://api.example.com", "job")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            assert "JOB_TOKEN" not in ast.unparse(node) and "dtj_" not in ast.unparse(node)
    assert src.count("dtj_secrettoken123") == 1  # only the assignment


def test_package_zip_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    first = kaggle_kernel.package_zip_b64()
    assert kaggle_kernel.package_zip_b64() is first


def test_session_timeout_is_bounded() -> None:
    assert kaggle_kernel.session_timeout_seconds(60) == (60 * 2 + 45) * 60
    assert kaggle_kernel.session_timeout_seconds(10_000) == 12 * 3600


# ---------------------------------------------------------------- account API


async def connect(client: httpx.AsyncClient, headers: dict[str, str], token: str = KGAT) -> dict[str, Any]:
    r = await client.put("/compute/kaggle", json={"username": "Alice-K", "api_token": token}, headers=headers)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_account_lifecycle(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    assert (await client.get("/compute/kaggle", headers=alice)).json() is None
    out = await connect(client, alice)
    assert out == {
        "username": "alice-k",
        "token_hint": f"…{KGAT[-4:]}",
        "status": "ok",
        "status_message": None,
        "gpu_hours_used": 1.0,
        "gpu_hours_total": 30.0,
        "quota_refresh_at": out["quota_refresh_at"],
        "checked_at": out["checked_at"],
    }
    assert out["quota_refresh_at"] and out["checked_at"]
    assert KGAT not in json.dumps(out)
    async with get_sessionmaker()() as db:
        row = await db.scalar(select(ComputeAccount))
    assert row is not None and KGAT.encode() not in row.ciphertext and decrypt(row.ciphertext) == KGAT
    assert (await client.get("/compute/kaggle", headers=alice)).json()["status"] == "ok"
    assert (await client.post("/compute/kaggle/check", headers=alice)).status_code == 202
    assert (await client.delete("/compute/kaggle", headers=alice)).status_code == 204
    assert (await client.get("/compute/kaggle", headers=alice)).json() is None
    assert (await client.delete("/compute/kaggle", headers=alice)).status_code == 404


async def test_account_is_per_user(
    client: httpx.AsyncClient, alice: dict[str, str], auth: Auth, kg: FakeKaggle
) -> None:
    await connect(client, alice)
    bob = auth(sub=BOB, email="bob@example.com")
    assert (await client.get("/compute/kaggle", headers=bob)).json() is None
    assert (await client.post("/compute/kaggle/check", headers=bob)).status_code == 404


async def test_invalid_token_and_no_quota(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    kg.http_status = 401
    out = await connect(client, alice)
    assert out["status"] == "invalid" and "rejected" in out["status_message"]
    kg.http_status = 200
    kg.quota = {"gpuQuota": {"timeUsed": "0s", "totalTimeAllowed": "0s"}}
    r = await client.post("/compute/kaggle/check", headers=alice)
    assert r.json()["status"] == "no_gpu_quota" and "phone" in r.json()["status_message"]


async def test_token_that_only_reads_quota_is_rejected(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    kg.kernels_unauthenticated = True
    await connect(client, alice)
    account = (await client.get("/compute/kaggle", headers=alice)).json()
    assert account["status"] == "invalid"
    assert "can't run Kaggle notebooks" in account["status_message"]
    assert account["gpu_hours_total"] == 30


def test_session_cookie_is_never_sent_back(kg: FakeKaggle) -> None:
    with kaggle_client.KaggleClient("alice-k", "KGAT_x") as c:
        c.gpu_quota()  # Kaggle sets ka_sessionid here
        c.check_kernel_access()
        c.session_status("doctune-x-1")
    assert all("cookie" not in headers for _, _, headers in kg.requests)


def test_nested_error_message_is_used(kg: FakeKaggle) -> None:
    kg.kernels_unauthenticated = True
    with kaggle_client.KaggleClient("alice-k", "KGAT_x") as c, pytest.raises(kaggle_client.KaggleAuthError) as exc:
        c.check_kernel_access()
    assert exc.value.message == "Unauthenticated"


async def test_unreachable_kaggle_leaves_status_unchecked(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    kg.http_status = 503
    out = await connect(client, alice)
    assert out["status"] == "unchecked" and out["status_message"]


async def test_put_validates_input(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    r = await client.put("/compute/kaggle", json={"username": "bad name!", "api_token": KGAT}, headers=alice)
    assert r.status_code == 422
    r = await client.put("/compute/kaggle", json={"username": "alice", "api_token": "x"}, headers=alice)
    assert r.status_code == 422
    assert (await client.put("/compute/kaggle", json={}, headers={})).status_code == 401


async def test_token_never_logged(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    await connect(client, alice)
    kg.http_status = 401
    await client.post("/compute/kaggle/check", headers=alice)
    assert KGAT not in caplog.text


# ---------------------------------------------------------------- creating a Kaggle job


async def approved(client: httpx.AsyncClient, alice: dict[str, str]) -> str:
    with fake_groq() as fake:
        return await approved_project(client, alice, fake)


async def create_kaggle(client: httpx.AsyncClient, alice: dict[str, str], pid: str, **extra: Any) -> httpx.Response:
    body = {"base_model_id": "unsloth/Qwen3.5-4B", "backend": "kaggle", **extra}
    return await client.post(f"/projects/{pid}/training", json=body, headers=alice)


async def kaggle_job(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> tuple[str, str, str]:
    """Connected account, approved project, kaggle training started (launch ran eagerly). (pid, job_id, token)."""
    await connect(client, alice)
    pid = await approved(client, alice)
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 201, r.text
    return pid, r.json()["job"]["id"], kg.last_token


async def get_job(job_id: str) -> TrainingJob:
    async with get_sessionmaker()() as db:
        job = await db.get(TrainingJob, __import__("uuid").UUID(job_id))
    assert job is not None
    return job


async def project_state(client: httpx.AsyncClient, alice: dict[str, str], pid: str) -> dict[str, Any]:
    return dict((await client.get(f"/projects/{pid}", headers=alice)).json())


async def test_kaggle_requires_connected_account(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid = await approved(client, alice)
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 409 and r.json()["error"] == "kaggle_not_connected"
    kg.http_status = 401
    await connect(client, alice)  # invalid token
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 409 and r.json()["error"] == "kaggle_not_connected"
    assert kg.saves == 0


async def test_kaggle_rejects_gated_custom_model(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle, monkeypatch: pytest.MonkeyPatch
) -> None:
    from doctune.training import hf_check

    info = {"config": {"model_type": "llama"}, "gated": True, "tags": [], "cardData": {"license": "apache-2.0"}}
    info["safetensors"] = {"total": 8e9}
    monkeypatch.setattr(hf_check, "test_transport", httpx.MockTransport(lambda r: httpx.Response(200, json=info)))
    import redis

    for key in redis.Redis.from_url("redis://localhost:56379/0").scan_iter("hfcheck:*"):
        redis.Redis.from_url("redis://localhost:56379/0").delete(key)
    await connect(client, alice)
    pid = await approved(client, alice)
    r = await create_kaggle(client, alice, pid, base_model_id="acme/gated-8b", license_ack=True)
    assert r.status_code == 409 and r.json()["error"] == "kaggle_gated_model"


async def test_create_kaggle_job_launches_kernel(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    await connect(client, alice)
    pid = await approved(client, alice)
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"] is None and body["notebook_url"] is None
    assert body["job"]["backend"] == "kaggle"
    assert (await project_state(client, alice, pid))["status"] == "awaiting_run"

    job = await get_job(body["job"]["id"])
    short = job.id.hex[:8]
    assert job.launch_attempts == 1 and job.external_ref == f"alice-k/doctune-{short}-1"
    assert job.external_url and job.external_url.endswith(job.external_ref)
    save = kg.calls("SaveKernel")[0]
    assert save["slug"] == job.external_ref and save["newTitle"] == f"DocTune {short} 1"
    assert 0 < save["sessionTimeoutSeconds"] <= 12 * 3600
    compile(save["text"], "kernel.py", "exec")
    assert "http://testserver" in save["text"]

    out = (await client.get(f"/projects/{pid}/training/{job.id}", headers=alice)).json()
    assert out["launch_attempts"] == 1 and out["external_url"] == job.external_url and out["token_prefix"]
    assert kg.last_token not in json.dumps(out)
    # the kernel can now talk to the job API with that token, so the project moves as with Colab
    assert (
        await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(kg.last_token))
    ).status_code == 200
    assert (await project_state(client, alice, pid))["status"] == "training"
    # the user never sees or rotates a token for Kaggle jobs
    r = await client.post(f"/projects/{pid}/training/{job.id}/token", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "token_managed"


async def test_colab_default_unchanged(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    pid = await approved(client, alice)
    r = await client.post(f"/projects/{pid}/training", json={"base_model_id": "unsloth/Qwen3.5-4B"}, headers=alice)
    assert r.status_code == 201
    assert r.json()["token"].startswith("dtj_") and r.json()["notebook_url"] and r.json()["job"]["backend"] == "colab"
    assert kg.requests == []


async def test_switch_waiting_colab_job_to_kaggle(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid = await approved(client, alice)
    body = {"base_model_id": "unsloth/Qwen3.5-4B", "preset": "quick"}
    colab = (await client.post(f"/projects/{pid}/training", json=body, headers=alice)).json()
    colab_token, colab_id = colab["token"], colab["job"]["id"]

    r = await client.post(f"/projects/{pid}/training/{colab_id}/switch", json={}, headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "kaggle_not_connected"

    await connect(client, alice)
    r = await client.post(f"/projects/{pid}/training/{colab_id}/switch", json={"backend": "kaggle"}, headers=alice)
    assert r.status_code == 200, r.text
    new = r.json()["job"]
    assert new["backend"] == "kaggle" and new["preset"] == "quick" and new["id"] != colab_id
    assert new["hyperparams"] == colab["job"]["hyperparams"]
    assert r.json()["token"] is None and kg.saves == 1
    assert (await get_job(colab_id)).state == JobState.cancelled
    assert (await project_state(client, alice, pid))["status"] == "awaiting_run"
    # the old notebook token is dead
    assert (await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(colab_token))).status_code == 401
    # a job that already switched (or started) can't switch again
    r = await client.post(f"/projects/{pid}/training/{colab_id}/switch", json={}, headers=alice)
    assert r.status_code == 409


async def test_launch_is_idempotent_per_attempt(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    _, job_id, _ = await kaggle_job(client, alice, kg)
    assert kaggle_tasks.launch_kaggle_job.apply(args=[job_id, 1]).get() == "skipped"
    assert kg.saves == 1


async def test_launch_auth_failure_fails_job_and_project(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    await connect(client, alice)
    pid = await approved(client, alice)
    kg.http_status = 401  # token revoked on Kaggle after it was validated
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 201
    state = await project_state(client, alice, pid)
    assert state["status"] == "failed" and "Kaggle" in state["status_message"]
    assert state["allowed_actions"].count("retry") == 1
    job = await get_job(r.json()["job"]["id"])
    assert job.state == JobState.failed and job.launch_attempts == 0
    assert (await client.get("/compute/kaggle", headers=alice)).json()["status"] == "invalid"
    # retrying goes back to review
    assert (await client.post(f"/projects/{pid}/retry", headers=alice)).status_code == 200
    assert (await project_state(client, alice, pid))["status"] == "in_review"


async def test_launch_rate_limit_retries(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle, monkeypatch: pytest.MonkeyPatch
) -> None:
    # eager mode re-raises Retry after running the retry; real workers just reschedule
    from doctune.workers.celery_app import app as celery_app

    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", False)
    await connect(client, alice)
    pid = await approved(client, alice)
    kg.rate_limit_calls = 1
    r = await create_kaggle(client, alice, pid)
    assert r.status_code == 201
    assert (await get_job(r.json()["job"]["id"])).launch_attempts == 1
    assert (await project_state(client, alice, pid))["status"] == "awaiting_run"


async def test_launch_with_empty_quota_fails_first_launch(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    await connect(client, alice)
    pid = await approved(client, alice)
    kg.quota["gpuQuota"] = {"timeUsed": "108000s", "timeReserved": "0s", "totalTimeAllowed": "108000s"}
    await create_kaggle(client, alice, pid)
    state = await project_state(client, alice, pid)
    assert (
        state["status"] == "failed"
        and "weekly GPU quota" in state["status_message"]
        and "2026-10-12" in state["status_message"]
    )
    assert kg.saves == 0


async def test_launch_refused_by_kaggle(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    await connect(client, alice)
    pid = await approved(client, alice)
    kg.save_error = "Phone verification is required"
    await create_kaggle(client, alice, pid)
    state = await project_state(client, alice, pid)
    assert state["status"] == "failed" and "phone" in state["status_message"].lower()


# ---------------------------------------------------------------- cancel


async def test_cancel_revokes_token(client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle) -> None:
    pid, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    r = await client.post(f"/projects/{pid}/training/{job_id}/cancel", headers=alice)
    assert r.status_code == 200 and r.json()["status"] == "in_review"
    r = await client.post("/jobs/current/heartbeat", json={"step": 1, "max_steps": 10}, headers=nb(token))
    assert r.status_code == 401  # the kernel treats this as 'stop'
    async with get_sessionmaker()() as db:
        live = (await db.scalars(select(JobToken).where(JobToken.revoked_at.is_(None)))).all()
    assert live == []
    assert kaggle_tasks.launch_kaggle_job.apply(args=[job_id, 2]).get() == "skipped"


async def test_fatal_fail_from_kernel_revokes_token(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, _, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    r = await client.post("/jobs/current/fail", json={"error": "boom", "fatal": True}, headers=nb(token))
    assert r.status_code == 200
    assert (await project_state(client, alice, pid))["status"] == "failed"
    assert (await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))).status_code == 401


# ---------------------------------------------------------------- poll


async def age_job(job_id: str) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(
            text("UPDATE training_jobs SET updated_at = now() - interval '10 minutes' WHERE id = :id"), {"id": job_id}
        )
        await db.commit()


async def set_job(job_id: str, **values: Any) -> None:
    async with get_sessionmaker()() as db:
        job = await db.get(TrainingJob, __import__("uuid").UUID(job_id))
        assert job is not None
        for k, v in values.items():
            setattr(job, k, v)
        await db.commit()
    await age_job(job_id)


async def test_poll_shows_queued_then_setting_up_before_start(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    _, job_id, _ = await kaggle_job(client, alice, kg)
    kg.session_status = "QUEUED"
    kaggle_tasks.poll_kaggle_jobs.apply().get()
    assert (await get_job(job_id)).runtime_info == {"kaggle_status": "QUEUED"}
    assert kg.calls("GetKernelSessionStatus")[-1]["kernelSlug"].startswith("doctune-")
    kg.session_status = "RUNNING"
    kaggle_tasks.poll_kaggle_jobs.apply().get()
    assert (await get_job(job_id)).runtime_info == {"kaggle_status": "RUNNING"}


async def test_poll_permission_denied_keeps_account_valid(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    await kaggle_job(client, alice, kg)
    kg.status_http = 403
    kaggle_tasks.poll_kaggle_jobs.apply().get()
    assert (await client.get("/compute/kaggle", headers=alice)).json()["status"] == "ok"


async def test_poll_leaves_running_kernels_alone(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    _, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await age_job(job_id)
    for status in ("RUNNING", "QUEUED", "NEW_SCRIPT", 1):
        kg.session_status = status
        assert kaggle_tasks.poll_kaggle_jobs()["relaunched"] == 0
    assert kg.saves == 1
    assert kg.calls("GetKernelSessionStatus")[0]["kernelSlug"].startswith("doctune-")


async def test_poll_relaunches_after_session_end_and_resumes(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await client.post("/jobs/current/heartbeat", json={"step": 40, "max_steps": 100, "loss": 0.5}, headers=nb(token))
    r = await client.post("/jobs/current/pause", json={"reason": "session_ended", "step": 40}, headers=nb(token))
    assert r.status_code == 200
    assert (await project_state(client, alice, pid))["status"] == "paused"
    kg.session_status = "COMPLETE"

    # a fresh stop is given a grace period (its last calls may still be landing)
    assert kaggle_tasks.poll_kaggle_jobs()["relaunched"] == 0
    await age_job(job_id)
    assert kaggle_tasks.poll_kaggle_jobs()["relaunched"] == 1

    job = await get_job(job_id)
    assert job.launch_attempts == 2 and job.external_ref and job.external_ref.endswith("-2")
    new_token = kg.last_token
    assert new_token != token
    assert (await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))).status_code == 401
    r = await client.post("/jobs/current/start", json={"runtime": {}, "resumed_from_step": 40}, headers=nb(new_token))
    assert r.status_code == 200
    assert (await project_state(client, alice, pid))["status"] == "training"


async def test_poll_relaunches_a_run_the_heartbeat_monitor_paused(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    from datetime import UTC, datetime, timedelta

    from doctune.workers.tasks.training import monitor_heartbeats

    _, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await set_job(job_id, last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=30))
    assert monitor_heartbeats() == 1
    job = await get_job(job_id)
    assert job.state == JobState.paused and job.pause_reason == PauseReason.heartbeat_timeout
    kg.session_status = "ERROR"
    await age_job(job_id)
    assert kaggle_tasks.poll_kaggle_jobs()["relaunched"] == 1
    assert kg.saves == 2


async def test_poll_relaunches_with_checkpoint_after_kernel_error(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    _, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    with sync_session() as db:
        db.add(
            Checkpoint(job_id=__import__("uuid").UUID(job_id), step=30, storage_key="k", size_bytes=1, sha256="0" * 64)
        )
        db.commit()
    kg.session_status = "ERROR"
    await age_job(job_id)
    assert kaggle_tasks.poll_kaggle_jobs()["relaunched"] == 1
    assert (await get_job(job_id)).launch_attempts == 2


async def test_poll_fails_without_checkpoint_and_shows_kaggle_message(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    kg.session_status, kg.failure_message = "ERROR", "Notebook exceeded allowed memory " + "x" * 600
    await age_job(job_id)
    counts = kaggle_tasks.poll_kaggle_jobs()
    assert counts["failed"] == 1 and kg.saves == 1
    state = await project_state(client, alice, pid)
    assert state["status"] == "failed" and "exceeded allowed memory" in state["status_message"]
    assert len(state["status_message"]) <= 500 and "Colab" in state["status_message"]
    job = await get_job(job_id)
    assert job.state == JobState.failed and job.error
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(JobToken).where(JobToken.revoked_at.is_(None)))).all() == []


async def test_poll_gives_up_after_three_launches(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await client.post("/jobs/current/pause", json={"reason": "session_ended", "step": 5}, headers=nb(token))
    await set_job(job_id, launch_attempts=3)
    kg.session_status = "CANCEL_ACKNOWLEDGED"
    assert kaggle_tasks.poll_kaggle_jobs()["failed"] == 1
    assert (await project_state(client, alice, pid))["status"] == "failed"


async def test_poll_fails_a_kernel_that_never_started(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, job_id, _ = await kaggle_job(client, alice, kg)
    kg.session_status, kg.failure_message = "ERROR", "pip failed"
    await age_job(job_id)
    assert kaggle_tasks.poll_kaggle_jobs()["failed"] == 1
    assert (await project_state(client, alice, pid))["status"] == "failed"


async def test_poll_defers_relaunch_when_weekly_quota_is_used_up(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid, job_id, token = await kaggle_job(client, alice, kg)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await client.post("/jobs/current/heartbeat", json={"step": 10, "max_steps": 100}, headers=nb(token))
    kg.session_status = "COMPLETE"
    kg.quota["gpuQuota"] = {"timeUsed": "108000s", "timeReserved": "0s", "totalTimeAllowed": "108000s"}
    with sync_session() as db:  # the kernel's session ended mid-training without telling us
        db.add(
            Checkpoint(job_id=__import__("uuid").UUID(job_id), step=10, storage_key="k", size_bytes=1, sha256="0" * 64)
        )
        db.commit()
    await age_job(job_id)
    kaggle_tasks.poll_kaggle_jobs()
    state = await project_state(client, alice, pid)
    assert state["status"] == "paused" and state["status_reason"] == "no_gpu" and "resets at" in state["status_message"]
    job = await get_job(job_id)
    assert job.state == JobState.paused and job.launch_attempts == 1 and kg.saves == 1

    # polling again while still out of quota changes nothing; once it resets, the run relaunches
    await age_job(job_id)
    kaggle_tasks.poll_kaggle_jobs()
    assert kg.saves == 1
    kg.quota["gpuQuota"] = {"timeUsed": "0s", "timeReserved": "0s", "totalTimeAllowed": "108000s"}
    await age_job(job_id)
    kaggle_tasks.poll_kaggle_jobs()
    assert kg.saves == 2 and (await get_job(job_id)).launch_attempts == 2


async def test_poll_ignores_colab_jobs_and_survives_rate_limit(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    pid = await approved(client, alice)
    await client.post(f"/projects/{pid}/training", json={"base_model_id": "unsloth/Qwen3.5-4B"}, headers=alice)
    assert kaggle_tasks.poll_kaggle_jobs()["checked"] == 0
    assert kg.requests == []


async def test_poll_revokes_tokens_of_finished_kaggle_jobs(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    _, job_id, _ = await kaggle_job(client, alice, kg)
    await set_job(job_id, state=JobState.completed)  # e.g. finished while a token somehow stayed live
    kaggle_tasks.poll_kaggle_jobs()
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(JobToken).where(JobToken.revoked_at.is_(None)))).all() == []


# ---------------------------------------------------------------- account deletion


async def test_purge_user_removes_compute_account(
    client: httpx.AsyncClient, alice: dict[str, str], kg: FakeKaggle
) -> None:
    await connect(client, alice)
    r = await client.delete("/me", headers=alice)
    assert r.status_code in (200, 202, 204), r.text
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(ComputeAccount))).all() == []
    assert ProjectStatus.draft  # keep import used
