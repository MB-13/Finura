import json
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fake_llm import fake_groq
from fixtures import LOREM
from flows import ready_project
from helpers import ALICE, BOB, create_project

from doctune.core.db import get_sessionmaker, sync_session
from doctune.core.storage import get_storage
from doctune.inference import manager
from doctune.models.training import Artifact, ArtifactKind, TrainingJob
from doctune.routers import playground

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


@pytest.fixture(autouse=True)
def clean_playground_state() -> Iterator[None]:
    import redis

    r = redis.Redis.from_url("redis://localhost:56379/0")
    for key in [*r.scan_iter("pg:*"), *r.scan_iter("playground:*")]:
        r.delete(key)
    yield
    for key in [*r.scan_iter("pg:*"), *r.scan_iter("playground:*")]:
        r.delete(key)


async def with_gguf(job_id: str) -> None:
    """Pretend the worker converted the adapter (llama.cpp isn't installed in tests)."""
    key = f"j/{job_id}/adapter/adapter.gguf"
    get_storage().write_bytes(key, b"GGUF-fake")
    async with get_sessionmaker()() as db:
        db.add(
            Artifact(
                job_id=uuid.UUID(job_id), kind=ArtifactKind.adapter_gguf, storage_key=key, size_bytes=9, uploaded=True
            )
        )
        await db.commit()


def mark_warm(job_id: str, source: str = "final") -> None:
    state = manager.ServerState(
        key=manager.server_key(job_id, source), port=8091, pid=1, started_at=time.time(), last_used=time.time()
    )
    import dataclasses

    manager._redis().set(manager.STATE_KEY, json.dumps(dataclasses.asdict(state)))


def fake_llama(tokens: list[str]) -> httpx.MockTransport:
    seen: list[dict] = []  # type: ignore[type-arg]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        lines = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in tokens]
        lines += [f"data: {json.dumps({'choices': [], 'usage': {'completion_tokens': len(tokens)}})}", "data: [DONE]"]
        return httpx.Response(200, text="\n\n".join(lines) + "\n\n", headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    transport.seen = seen  # type: ignore[attr-defined]
    return transport


def parse_sse(text: str) -> list[tuple[str, object]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        name = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name and data is not None:
            events.append((name, json.loads(data)))
    return events


async def test_status_explains_unavailability(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is False and "Train a model" in s["reason"]
    assert s["reason_code"] == "no_model"


async def test_models_above_the_server_limit_are_refused_unless_raised(
    client: httpx.AsyncClient, alice: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import update

    from doctune.core.config import get_settings
    from doctune.core.db import get_sessionmaker
    from doctune.models.training import TrainingJob

    with fake_groq() as fake:
        pid, job_id = await ready_project(client, alice, fake)
    async with get_sessionmaker()() as db:
        await db.execute(update(TrainingJob).where(TrainingJob.id == job_id).values(base_model_id="unsloth/Qwen3-8B"))
        await db.commit()
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is False and s["reason_code"] == "too_large"
    assert "Qwen3 8B" in s["reason"] and "up to 4.5B" in s["reason"]

    monkeypatch.setattr(get_settings(), "playground_max_params_b", 8.0)
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["reason_code"] == "preparing"


async def test_chat_streams_tokens_with_rag_sources(
    client: httpx.AsyncClient, alice: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_groq() as fake:
        pid, job_id = await ready_project(client, alice, fake)
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is False and "being prepared" in s["reason"]

    await with_gguf(job_id)
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s == {
        "available": True,
        "reason": None,
        "reason_code": None,
        "state": "cold",
        "source": "final",
        "checkpoint_step": None,
        "model": "unsloth/Qwen3.5-4B",
    }

    r = await client.post(
        f"/projects/{pid}/playground/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers=alice
    )
    assert r.status_code == 409 and r.json()["error"] == "warming_up"

    mark_warm(job_id)
    transport = fake_llama(["Hello", " there", "!"])
    monkeypatch.setattr(playground, "test_transport", transport)
    r = await client.post(
        f"/projects/{pid}/playground/chat",
        json={"messages": [{"role": "user", "content": "Section 3 fact. " + LOREM}], "compare_base": True},
        headers=alice,
    )
    assert r.status_code == 200
    events = parse_sse(r.text)
    assert [e for e, _ in events if e == "token"] == ["token"] * 3
    assert "".join(d["text"] for e, d in events if e == "token") == "Hello there!"  # type: ignore[index]
    sources = next(d for e, d in events if e == "sources")
    assert sources and "section_path" in sources[0]  # type: ignore[index]
    assert events[-1][0] == "done"

    sent = transport.seen[0]  # type: ignore[attr-defined]
    assert sent["messages"][0]["role"] == "system" and "CONTEXT" in sent["messages"][0]["content"]
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    assert sent["lora"] == [{"id": 0, "scale": 0.0}]
    assert sent["max_tokens"] <= 512


async def test_chat_limits_and_access(
    client: httpx.AsyncClient, alice: dict[str, str], auth: Auth, monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_groq() as fake:
        pid, job_id = await ready_project(client, alice, fake)
    await with_gguf(job_id)
    mark_warm(job_id)
    monkeypatch.setattr(playground, "test_transport", fake_llama(["ok"]))
    body = {"messages": [{"role": "user", "content": "hi"}], "use_rag": False}

    bob = auth(sub=BOB)
    assert (await client.post(f"/projects/{pid}/playground/chat", json=body, headers=bob)).status_code == 404

    import redis

    redis.Redis.from_url("redis://localhost:56379/0").set(f"pg:busy:{ALICE}", "1", ex=30)
    r = await client.post(f"/projects/{pid}/playground/chat", json=body, headers=alice)
    assert r.status_code == 429  # one answer at a time

    bad = await client.post(f"/projects/{pid}/playground/chat", json={**body, "max_tokens": 4096}, headers=alice)
    assert bad.status_code == 422


def test_manager_loads_swaps_and_stops_real_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Process control with a harmless stand-in for llama-server."""
    started: list[subprocess.Popen[bytes]] = []

    def fake_spawn(base: Path, adapter: Path, port: int) -> subprocess.Popen[bytes]:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        started.append(proc)
        return proc

    monkeypatch.setattr(manager, "spawn", fake_spawn)
    monkeypatch.setattr(manager, "wait_healthy", lambda url, timeout=0: True)
    monkeypatch.setattr(manager, "base_gguf_path", lambda repo, f: tmp_path / "base.gguf")
    get_storage().write_bytes("j/x/adapter/adapter.gguf", b"GGUF")
    try:
        first = manager.load("job1:final", "repo", "file", "j/x/adapter/adapter.gguf")
        assert manager.current() is not None and manager.current().key == "job1:final"  # type: ignore[union-attr]
        again = manager.load("job1:final", "repo", "file", "j/x/adapter/adapter.gguf")
        assert again.pid == first.pid and len(started) == 1  # already warm: no restart

        second = manager.load("job2:final", "repo", "file", "j/x/adapter/adapter.gguf")
        assert second.pid != first.pid
        started[0].wait(timeout=5)  # the previous server was stopped
        assert started[0].returncode is not None

        state = manager.current()
        assert state is not None
        state.last_used = time.time() - manager.IDLE_SECONDS - 1
        import dataclasses

        manager._redis().set(manager.STATE_KEY, json.dumps(dataclasses.asdict(state)))
        assert manager.stop_if_idle() is True
        started[1].wait(timeout=5)
        assert manager.current() is None
    finally:
        for p in started:
            if p.poll() is None:
                p.kill()


async def test_convert_adapter_creates_gguf_artifact(
    client: httpx.AsyncClient, alice: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from doctune.core.config import get_settings
    from doctune.workers.tasks import models as model_tasks

    with fake_groq() as fake:
        pid, job_id = await ready_project(client, alice, fake)

    def fake_convert(adapter_dir: Path, base_dir: Path, out_file: Path) -> None:
        assert (adapter_dir / "adapter_model.safetensors").exists()
        out_file.write_bytes(b"GGUF-converted")

    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is False and "still being prepared" in s["reason"]
    with sync_session() as db:
        job = db.get(TrainingJob, uuid.UUID(job_id))
        assert job is not None
        ended_at = job.ended_at
        job.ended_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is False and "couldn't prepare" in s["reason"]
    with sync_session() as db:
        job = db.get(TrainingJob, uuid.UUID(job_id))
        assert job is not None
        job.ended_at = ended_at
        db.commit()

    monkeypatch.setattr(get_settings(), "llama_cpp_dir", tmp_path)
    monkeypatch.setattr(model_tasks, "fetch_base_config", lambda model_id, cache: tmp_path)
    monkeypatch.setattr(model_tasks, "run_convert", fake_convert)
    assert model_tasks.convert_adapter(job_id, "final") == f"j/{job_id}/adapter/adapter.gguf"
    s = (await client.get(f"/projects/{pid}/playground/status", headers=alice)).json()
    assert s["available"] is True

    # a zip without adapter files is rejected, and a mismatched base model too
    with pytest.raises(model_tasks.ConvertError):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("readme.txt", "nope")
        model_tasks.extract_adapter(buf.getvalue(), tmp_path)

    import io as _io
    import zipfile as _zip

    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("adapter_config.json", json.dumps({"base_model_name_or_path": "meta-llama/Llama-3-8B"}))
        z.writestr("adapter_model.safetensors", b"\x00")
    get_storage().write_bytes(f"j/{job_id}/adapter/adapter.zip", buf.getvalue())
    assert model_tasks.convert_adapter(job_id, "final") is None  # logged and skipped
