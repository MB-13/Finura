"""Phases 3-5: training jobs, the notebook API (fake notebook), pause/resume, finish, evaluation."""

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fake_llm import fake_groq
from flows import approved_project
from helpers import ALICE, BOB, create_project, local_path
from sqlalchemy import select, update

from doctune.core.db import get_sessionmaker
from doctune.core.jobauth import hash_token
from doctune.core.storage import get_storage
from doctune.models.training import JobToken, TrainingJob
from doctune.models.user import EmailLog

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


def nb(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def state(client: httpx.AsyncClient, alice: dict[str, str], pid: str) -> dict:  # type: ignore[type-arg]
    return dict((await client.get(f"/projects/{pid}", headers=alice)).json())


async def put_signed(client: httpx.AsyncClient, upload: dict, data: bytes) -> None:  # type: ignore[type-arg]
    r = await client.put(local_path(upload["url"]), content=data, headers=upload["headers"])
    assert r.status_code == 204, r.text


def adapter_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("adapter_config.json", json.dumps({"base_model_name_or_path": "unsloth/Qwen3.5-4B"}))
        z.writestr("adapter_model.safetensors", b"\x00" * 128)
    return buf.getvalue()


async def start_training(client: httpx.AsyncClient, alice: dict[str, str]) -> tuple[str, str, str]:
    with fake_groq() as fake:
        pid = await approved_project(client, alice, fake)
    r = await client.post(f"/projects/{pid}/training", json={"base_model_id": "unsloth/Qwen3.5-4B"}, headers=alice)
    assert r.status_code == 201, r.text
    body = r.json()
    return pid, body["job"]["id"], body["token"]


async def test_catalog_and_presets(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    models = (await client.get("/models/catalog", headers=alice)).json()
    default = next(m for m in models if m["recommended"])
    assert default["id"] == "unsloth/Qwen3.5-4B" and default["train_mode"] == "lora16"
    assert set(default["est_minutes"]) == {"quick", "balanced", "thorough"}
    big = next(m for m in models if m["id"] == "unsloth/Qwen3-8B")
    assert big["playground_supported"] is False
    presets = {p["key"] for p in (await client.get("/training/presets", headers=alice)).json()}
    assert presets == {"quick", "balanced", "thorough"}


async def test_training_requires_approved_dataset(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/training", json={"base_model_id": "unsloth/Qwen3.5-4B"}, headers=alice)
    assert r.status_code == 409


async def test_full_training_lifecycle(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid, job_id, token = await start_training(client, alice)
    assert token.startswith("dtj_")
    s = await state(client, alice, pid)
    assert s["status"] == "awaiting_run"
    assert s["active_job"]["token_prefix"] == token[:10]
    assert token not in json.dumps(s)
    async with get_sessionmaker()() as db:
        row = await db.scalar(select(JobToken))
    assert row is not None and row.token_hash == hash_token(token)  # only the hash is stored

    # notebook: config
    cfg = (await client.get("/jobs/current/config", params={"notebook_version": "0.1.0"}, headers=nb(token))).json()
    assert cfg["job_id"] == job_id and cfg["train_mode"] == "lora16"
    assert cfg["max_steps"] > 0 and cfg["lib_versions"]["unsloth"] == "2026.10.1"
    train = await client.get(local_path(cfg["dataset"]["train_url"]))
    assert hashlib.sha256(train.content).hexdigest() == cfg["dataset"]["sha256_train"]
    old = await client.get("/jobs/current/config", params={"notebook_version": "0.0.1"}, headers=nb(token))
    assert old.status_code == 426

    # start + heartbeats
    r = await client.post(
        "/jobs/current/start", json={"runtime": {"gpu_name": "Tesla T4", "vram_gb": 15.6}}, headers=nb(token)
    )
    assert r.status_code == 200
    assert (await state(client, alice, pid))["status"] == "training"
    for step in (10, 20, 30):
        r = await client.post(
            "/jobs/current/heartbeat", json={"step": step, "max_steps": 100, "loss": 1.0 / step}, headers=nb(token)
        )
        assert r.json() == {"ok": True, "cancel_requested": False}
    metrics = (await client.get(f"/projects/{pid}/training/{job_id}/metrics", headers=alice)).json()
    assert [m["step"] for m in metrics] == [10, 20, 30]

    # checkpoint upload + latest
    ckpt = b"checkpoint-bytes" * 100
    up = (
        await client.post(
            "/jobs/current/checkpoint/upload-url", json={"size_bytes": len(ckpt), "step": 30}, headers=nb(token)
        )
    ).json()
    await put_signed(client, up, ckpt)
    r = await client.post(
        "/jobs/current/checkpoint/complete",
        json={"sha256": hashlib.sha256(ckpt).hexdigest(), "size_bytes": len(ckpt), "step": 30},
        headers=nb(token),
    )
    assert r.status_code == 200
    latest = (await client.get("/jobs/current/checkpoint/latest", headers=nb(token))).json()
    assert latest["exists"] and latest["step"] == 30
    assert (await client.get(local_path(latest["url"]))).content == ckpt

    # notebook reports a pause, then resumes
    await client.post("/jobs/current/pause", json={"reason": "idle_timeout", "step": 30}, headers=nb(token))
    s = await state(client, alice, pid)
    assert s["status"] == "paused" and "idle" in s["status_message"] and "30%" in s["status_message"]
    await client.post("/jobs/current/start", json={"runtime": {}, "resumed_from_step": 30}, headers=nb(token))
    assert (await state(client, alice, pid))["status"] == "training"

    # training done -> evaluating; uploads; finish -> ready
    await client.post(
        "/jobs/current/training-complete", json={"final_step": 100, "final_loss": 0.05}, headers=nb(token)
    )
    assert (await state(client, alice, pid))["status"] == "evaluating"
    r = await client.post("/jobs/current/finish", json={}, headers=nb(token))
    assert r.status_code == 409 and r.json()["error"] == "adapter_missing"

    adapter = adapter_zip()
    up = (
        await client.post(
            "/jobs/current/artifacts/upload-url",
            json={"kind": "adapter_safetensors", "size_bytes": len(adapter)},
            headers=nb(token),
        )
    ).json()
    await put_signed(client, up, adapter)
    r = await client.post(
        "/jobs/current/artifacts/complete",
        json={"kind": "adapter_safetensors", "sha256": hashlib.sha256(adapter).hexdigest(), "size_bytes": len(adapter)},
        headers=nb(token),
    )
    assert r.status_code == 200

    gens = "\n".join(
        json.dumps({"question": f"q{i}", "reference": f"ref {i}", "base_answer": "meh", "tuned_answer": f"ref {i}"})
        for i in range(12)
    ).encode()
    up = (
        await client.post(
            "/jobs/current/artifacts/upload-url",
            json={"kind": "eval_generations", "size_bytes": len(gens)},
            headers=nb(token),
        )
    ).json()
    await put_signed(client, up, gens)
    with fake_groq():
        await client.post(
            "/jobs/current/artifacts/complete",
            json={"kind": "eval_generations", "sha256": hashlib.sha256(gens).hexdigest(), "size_bytes": len(gens)},
            headers=nb(token),
        )
    r = await client.post(
        "/jobs/current/finish",
        json={"metrics": {"rouge_l_base": 0.2, "rouge_l_tuned": 0.6}, "exports": {"drive_path": "/MyDrive/DocTune/x"}},
        headers=nb(token),
    )
    assert r.status_code == 200 and r.json()["project_url"].endswith(pid)

    s = await state(client, alice, pid)
    assert s["status"] == "ready"
    assert s["active_job"]["state"] == "completed"
    assert s["active_job"]["exports"] == {"drive_path": "/MyDrive/DocTune/x"}
    ev = s["evaluation"]
    assert ev["state"] == "done" and ev["n_items"] == 12
    assert ev["tuned_scores"]["overall"] > ev["base_scores"]["overall"]
    arts = (await client.get(f"/projects/{pid}/artifacts", headers=alice)).json()
    kinds = {a["kind"] for a in arts}
    assert "adapter_safetensors" in kinds
    adapter_art = next(a for a in arts if a["kind"] == "adapter_safetensors")
    dl = (await client.get(f"/projects/{pid}/artifacts/{adapter_art['id']}/download", headers=alice)).json()
    assert (await client.get(local_path(dl["url"]))).content == adapter

    # the job token no longer works after the job ended for state changes
    r = await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    assert r.status_code == 409


async def test_monitor_pauses_silent_jobs_and_emails_once(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    from doctune.workers.tasks.training import monitor_heartbeats

    pid, _job_id, token = await start_training(client, alice)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await client.post("/jobs/current/heartbeat", json={"step": 64, "max_steps": 100, "loss": 0.3}, headers=nb(token))
    async with get_sessionmaker()() as db:
        await db.execute(update(TrainingJob).values(last_heartbeat_at=datetime.now(UTC) - timedelta(minutes=20)))
        await db.commit()
    assert monitor_heartbeats() == 1
    assert monitor_heartbeats() == 0
    s = await state(client, alice, pid)
    assert s["status"] == "paused" and s["status_reason"] == "heartbeat_timeout"
    assert "64%" in s["status_message"]
    async with get_sessionmaker()() as db:
        emails = (await db.scalars(select(EmailLog).where(EmailLog.kind == "paused"))).all()
    assert len(emails) == 1

    # the user re-runs the notebook
    await client.post("/jobs/current/heartbeat", json={"step": 65, "max_steps": 100}, headers=nb(token))
    assert (await state(client, alice, pid))["status"] == "training"


async def test_token_rotation_expiry_and_scope(client: httpx.AsyncClient, alice: dict[str, str], auth: Auth) -> None:
    pid, job_id, token = await start_training(client, alice)
    new = (await client.post(f"/projects/{pid}/training/{job_id}/token", headers=alice)).json()["token"]
    r = await client.get("/jobs/current/config", headers=nb(token))
    assert r.status_code == 401 and r.json()["error"] == "token_revoked"
    assert (await client.get("/jobs/current/config", headers=nb(new))).status_code == 200

    async with get_sessionmaker()() as db:
        await db.execute(update(JobToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()
    r = await client.get("/jobs/current/config", headers=nb(new))
    assert r.status_code == 401 and r.json()["error"] == "token_expired"

    for bad in ("", "Bearer nope", "Bearer dtj_forged"):
        r = await client.get("/jobs/current/config", headers={"Authorization": bad})
        assert r.status_code == 401
    # a user JWT is not a job token, and job routes are not reachable by another user
    assert (await client.get("/jobs/current/config", headers=alice)).status_code == 401
    bob = auth(sub=BOB)
    assert (await client.get(f"/projects/{pid}/training/{job_id}", headers=bob)).status_code == 404


async def test_cancel_returns_to_review_and_revokes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid, job_id, token = await start_training(client, alice)
    r = await client.post(f"/projects/{pid}/training/{job_id}/cancel", headers=alice)
    assert r.json()["status"] == "in_review"
    assert (await client.get("/jobs/current/config", headers=nb(token))).status_code == 401


async def test_fatal_failure_allows_retry(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid, _job_id, token = await start_training(client, alice)
    await client.post("/jobs/current/start", json={"runtime": {}}, headers=nb(token))
    await client.post("/jobs/current/fail", json={"error": "out_of_memory at step 0", "fatal": True}, headers=nb(token))
    s = await state(client, alice, pid)
    assert s["status"] == "failed" and "smaller model" in s["status_message"]
    r = await client.post(f"/projects/{pid}/retry", headers=alice)
    assert r.json()["status"] == "in_review"


async def test_no_gpu_before_start_pauses(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid, _job_id, token = await start_training(client, alice)
    await client.post("/jobs/current/pause", json={"reason": "no_gpu", "step": 0}, headers=nb(token))
    s = await state(client, alice, pid)
    assert s["status"] == "paused" and "no free GPU" in s["status_message"]


async def test_checkpoint_size_mismatch(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    _pid, _job, token = await start_training(client, alice)
    up = (await client.post("/jobs/current/checkpoint/upload-url", json={"size_bytes": 10}, headers=nb(token))).json()
    await put_signed(client, up, b"0123456789")
    r = await client.post(
        "/jobs/current/checkpoint/complete", json={"sha256": "0" * 64, "size_bytes": 11}, headers=nb(token)
    )
    assert r.status_code == 409


async def test_retention_and_purge_remove_job_files(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    from doctune.workers.tasks.training import cleanup_retention

    pid, job_id, token = await start_training(client, alice)
    adapter = adapter_zip()
    up = (
        await client.post(
            "/jobs/current/artifacts/upload-url",
            json={"kind": "adapter_safetensors", "size_bytes": len(adapter)},
            headers=nb(token),
        )
    ).json()
    await put_signed(client, up, adapter)
    await client.post(
        "/jobs/current/artifacts/complete",
        json={"kind": "adapter_safetensors", "sha256": hashlib.sha256(adapter).hexdigest(), "size_bytes": len(adapter)},
        headers=nb(token),
    )
    storage = get_storage()
    assert storage.head(f"j/{job_id}/adapter/adapter.zip") is not None
    async with get_sessionmaker()() as db:
        await db.execute(update(TrainingJob).values(ended_at=datetime.now(UTC) - timedelta(days=15)))
        await db.commit()
    assert cleanup_retention() == 1
    assert storage.head(f"j/{job_id}/adapter/adapter.zip") is None
    assert (await client.get(f"/projects/{pid}/artifacts", headers=alice)).json() == []
