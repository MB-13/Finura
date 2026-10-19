"""End-to-end Phase 2 flow against the fake provider: style -> preview -> generate -> review -> approve."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fake_llm import FakeProvider, fake_groq
from fixtures import LOREM
from helpers import ALICE, create_project, upload
from sqlalchemy import update

from doctune.core.db import get_sessionmaker
from doctune.core.storage import get_storage
from doctune.models.generation import GenerationRun, GenState

Auth = Callable[..., dict[str, str]]

STYLE = {
    "description": "A friendly support agent. Short sentences, end by offering more help.",
    "tone": "friendly",
    "length": "short",
    "format": "plain",
    "language": "en",
    "examples": [
        {"input": "How do I reset it?", "output": "Hold the button for 5 seconds. Anything else?"},
        {"input": "Does it work offline?", "output": "Yes, the buttons still work offline. Anything else?"},
    ],
}


def long_markdown(sections: int = 10) -> bytes:
    body = "\n\n".join(f"## Topic {i}\n\n" + (f"Section {i} fact. " + LOREM) * 12 for i in range(sections))
    return f"# Manual\n\n{body}\n".encode()


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


async def ready_project(client: httpx.AsyncClient, alice: dict[str, str], fake: FakeProvider) -> str:
    """A project with parsed documents, a saved style and a working Groq key."""
    pid = str((await create_project(client, alice))["id"])
    await upload(client, alice, pid, "manual.md", long_markdown())
    await client.post(f"/projects/{pid}/process", headers=alice)
    await client.patch(f"/projects/{pid}", json={"target_pairs": 50}, headers=alice)
    await client.put("/keys/groq", json={"api_key": "gsk_test_1234567890"}, headers=alice)
    r = await client.put(f"/projects/{pid}/style", json=STYLE, headers=alice)
    assert r.status_code == 200, r.text
    return pid


async def project(client: httpx.AsyncClient, alice: dict[str, str], pid: str) -> dict[str, object]:
    return dict((await client.get(f"/projects/{pid}", headers=alice)).json())


async def test_style_rules(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = str((await create_project(client, alice))["id"])
    r = await client.put(f"/projects/{pid}/style", json=STYLE, headers=alice)
    assert r.status_code == 409  # documents not processed yet

    templates = (await client.get("/style-templates", headers=alice)).json()
    assert {t["key"] for t in templates} >= {"support_bot", "json_extractor"}

    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
    first = (await client.get(f"/projects/{pid}/style", headers=alice)).json()
    same = (await client.put(f"/projects/{pid}/style", json=STYLE, headers=alice)).json()
    assert same["id"] == first["id"]  # unchanged style -> same snapshot

    one = {**STYLE, "examples": STYLE["examples"][:1], "format": "json"}
    warned = (await client.put(f"/projects/{pid}/style", json=one, headers=alice)).json()
    codes = {w["code"] for w in warned["warnings"]}
    assert {"single_example", "examples_inconsistent"} <= codes
    assert warned["id"] != first["id"]

    bad = await client.put(f"/projects/{pid}/style", json={**STYLE, "examples": []}, headers=alice)
    assert bad.status_code == 422


async def test_full_flow(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)

        # generating before any preview is refused
        r = await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)
        assert r.status_code == 409 and r.json()["error"] == "preview_required"

        r = await client.post(f"/projects/{pid}/preview", json={"n_chunks": 3, "pairs_per_chunk": 2}, headers=alice)
        assert r.status_code == 202, r.text
        state = await project(client, alice, pid)
        assert state["status"] == "awaiting_style"
        preview = state["latest_preview"]
        assert preview["state"] == "done"  # type: ignore[index]
        pairs = (await client.get(f"/projects/{pid}/runs/{preview['id']}/pairs", headers=alice)).json()  # type: ignore[index]
        assert len(pairs) == 6
        assert pairs[0]["chunk"]["excerpt"]
        assert pairs[0]["judge_correctness"] == 5

        est = (await client.get(f"/projects/{pid}/estimate", headers=alice)).json()
        assert est["target_pairs"] == 50 and est["est_tokens"] > 0 and est["providers"] == ["groq"]

        fake.low_score_every = 10  # some pairs fail the quality check
        r = await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)
        assert r.status_code == 202, r.text

    state = await project(client, alice, pid)
    assert state["status"] == "in_review", state
    run = state["active_run"]
    assert run["state"] == "done"  # type: ignore[index]
    counts = state["counts"]
    assert counts["pairs_kept"] == 50  # type: ignore[index]
    assert counts["pairs_eval"] == 5  # type: ignore[index]

    stats = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
    assert stats["dropped_by_reason"]["judge_low"] > 0
    assert stats["dropped_by_reason"]["over_target"] > 0
    assert (stats["min_pairs"], stats["min_eval"]) == (50, 5)

    # previews never leak into the dataset
    listed = (await client.get(f"/projects/{pid}/pairs", params={"kept": True, "limit": 500}, headers=alice)).json()
    assert len(listed["items"]) == 50

    # review: edit, drop, add, bulk move
    first = listed["items"][0]
    r = await client.patch(f"/projects/{pid}/pairs/{first['id']}", json={"answer": "Edited answer."}, headers=alice)
    assert r.json()["edited"] is True
    r = await client.post(
        f"/projects/{pid}/pairs", json={"question": "My own question?", "answer": "Mine."}, headers=alice
    )
    assert r.status_code == 201
    ids = [p["id"] for p in listed["items"][1:3]]
    r = await client.post(f"/projects/{pid}/pairs/bulk", json={"ids": ids, "action": "drop"}, headers=alice)
    assert r.json()["updated"] == 2

    r = await client.post(f"/projects/{pid}/dataset/approve", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "dataset_too_small"  # 49 kept after dropping 2 and adding 1
    await client.post(f"/projects/{pid}/pairs/bulk", json={"ids": ids, "action": "restore"}, headers=alice)

    r = await client.post(f"/projects/{pid}/dataset/approve", headers=alice)
    assert r.status_code == 200, r.text
    version = r.json()
    assert version["train_count"] + version["eval_count"] == 51
    state = await project(client, alice, pid)
    assert state["dataset_version"]["id"] == version["id"]  # type: ignore[index]

    # the stored JSONL is chat format
    from doctune.core.db import get_sessionmaker as sm
    from doctune.models.generation import DatasetVersion

    async with sm()() as db:
        row = await db.get(DatasetVersion, version["id"])
    assert row is not None
    lines = get_storage().read_bytes(row.train_key).decode().strip().splitlines()
    record = json.loads(lines[0])
    assert [m["role"] for m in record["messages"]] == ["user", "assistant"]

    # editing after approval requires approving again
    await client.patch(f"/projects/{pid}/pairs/{first['id']}", json={"split": "train"}, headers=alice)
    assert (await project(client, alice, pid))["dataset_version"] is None

    export = (await client.post(f"/projects/{pid}/dataset/export", headers=alice)).json()
    assert "/storage/" in export["url"]

    r = await client.post(f"/projects/{pid}/dataset/restyle", headers=alice)
    assert r.json()["status"] == "awaiting_style"
    assert r.json()["counts"]["pairs_kept"] == 1  # only the user-added pair remains


async def test_quota_exhaustion_waits_then_resumes(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    from doctune.workers.tasks.generate import resume_runs

    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
        fake.mode = "daily_quota"
        await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)
        state = await project(client, alice, pid)
        assert state["status"] == "generating"
        assert state["active_run"]["state"] == "waiting_quota"  # type: ignore[index]
        keys = (await client.get("/keys", headers=alice)).json()
        assert keys[0]["status"] == "quota_exhausted"

        # quota resets: flip the provider back, clear cooldowns, make the run due
        fake.mode = "ok"
        import redis

        r = redis.Redis.from_url("redis://localhost:56379/0")
        for key in r.scan_iter("rl:*"):
            r.delete(key)
        async with get_sessionmaker()() as db:
            await db.execute(update(GenerationRun).values(resume_at=datetime.now(UTC) - timedelta(minutes=1)))
            await db.commit()
        assert resume_runs() == 1

    state = await project(client, alice, pid)
    assert state["status"] == "in_review"
    assert state["counts"]["pairs_kept"] == 50  # type: ignore[index]


async def test_cancel_generation(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
        fake.mode = "daily_quota"  # keeps the run waiting so it can be cancelled
        run = (await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)).json()
    r = await client.post(f"/projects/{pid}/runs/{run['id']}/cancel", headers=alice)
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_style"
    async with get_sessionmaker()() as db:
        row = await db.get(GenerationRun, run["id"])
    assert row is not None and row.state == GenState.cancelled


async def finished_early(client: httpx.AsyncClient, alice: dict[str, str], fake: FakeProvider) -> tuple[str, str]:
    """A run stopped while waiting for quota, finished early with 25 judged pairs."""
    from doctune.models.generation import DatasetPair

    pid = await ready_project(client, alice, fake)
    await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
    fake.mode = "daily_quota"
    run = (await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)).json()
    async with get_sessionmaker()() as db:
        db.add_all(
            DatasetPair(
                project_id=pid,
                run_id=run["id"],
                question=f"Question {i} about topic {i * 7}?",
                answer=f"Answer {i}.",
                kept=True,
                judge_correctness=5,
                judge_style=5,
            )
            for i in range(25)
        )
        await db.commit()
    r = await client.post(f"/projects/{pid}/runs/{run['id']}/finish", headers=alice)
    assert r.status_code == 200, r.text
    return pid, str(run["id"])


async def test_small_dataset_can_be_approved_on_purpose(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid, run_id = await finished_early(client, alice, fake)
    stats = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
    assert stats["kept"] < stats["min_pairs"] and stats["kept"] >= stats["small_min_pairs"]
    assert stats["min_eval"] == 1
    assert stats["resume"]["run_id"] == run_id and stats["resume"]["remaining_chunks"] > 0

    r = await client.post(f"/projects/{pid}/dataset/approve", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "dataset_too_small"
    r = await client.post(f"/projects/{pid}/dataset/approve", json={"allow_small": True}, headers=alice)
    assert r.status_code == 200, r.text
    assert r.json()["train_count"] + r.json()["eval_count"] == stats["kept"]


async def test_resume_completes_a_run_finished_early(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid, run_id = await finished_early(client, alice, fake)
        before = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()

        fake.mode = "ok"  # quota is back: clear the provider cooldowns
        import redis

        rds = redis.Redis.from_url("redis://localhost:56379/0")
        for key in rds.scan_iter("rl:*"):
            rds.delete(key)
        r = await client.post(f"/projects/{pid}/runs/{run_id}/resume", headers=alice)
        assert r.status_code == 202, r.text

    state = await project(client, alice, pid)
    assert state["status"] == "in_review"
    after = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
    assert after["kept"] > before["kept"]
    assert after["resume"] is None

    r = await client.post(f"/projects/{pid}/runs/{run_id}/resume", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "invalid_state"


async def test_finish_early_uses_pairs_so_far(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    from doctune.models.generation import DatasetPair

    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
        fake.mode = "daily_quota"  # the run waits for quota with nothing generated yet
        run = (await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)).json()
    state = await project(client, alice, pid)
    assert "finish_generation" in state["allowed_actions"]  # type: ignore[operator]

    r = await client.post(f"/projects/{pid}/runs/{run['id']}/finish", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "too_few_pairs"

    # pairs judged before the quota ran out, plus one generated but never judged
    async with get_sessionmaker()() as db:
        db.add_all(
            DatasetPair(
                project_id=pid,
                run_id=run["id"],
                question=f"Question {i} about topic?",
                answer=f"Answer {i}.",
                kept=True,
                judge_correctness=5,
                judge_style=5,
            )
            for i in range(25)
        )
        db.add(DatasetPair(project_id=pid, run_id=run["id"], question="Unjudged?", answer="Not scored."))
        await db.commit()

    r = await client.post(f"/projects/{pid}/runs/{run['id']}/finish", headers=alice)
    assert r.status_code == 200, r.text
    state = await project(client, alice, pid)
    assert state["status"] == "in_review"
    assert 0 < state["counts"]["pairs_kept"] <= 25  # type: ignore[index]
    async with get_sessionmaker()() as db:
        row = await db.get(GenerationRun, run["id"])
    assert row is not None and row.state == GenState.done

    r = await client.post(f"/projects/{pid}/runs/{run['id']}/finish", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "invalid_state"


async def test_preview_without_key(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
    await client.delete("/keys/groq", headers=alice)
    r = await client.post(f"/projects/{pid}/preview", json={}, headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "key_required"


async def test_preview_rate_limited_returns_to_style_with_message(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        fake.mode = "daily_quota"
        await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
    state = await project(client, alice, pid)
    assert state["status"] == "awaiting_style"
    assert "rate-limited" in str(state["status_message"])
    assert state["latest_preview"]["state"] == "failed"  # type: ignore[index]


async def test_generate_more_adds_to_the_reviewed_dataset(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2}, headers=alice)
        await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)
        stats = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
        assert stats["kept"] == 50 and stats["more"] is None  # target reached

        listed = (await client.get(f"/projects/{pid}/pairs", params={"kept": True, "limit": 500}, headers=alice)).json()
        ids = [p["id"] for p in listed["items"][:20]]
        await client.post(f"/projects/{pid}/pairs/bulk", json={"ids": ids, "action": "drop"}, headers=alice)
        edited = listed["items"][25]
        await client.patch(f"/projects/{pid}/pairs/{edited['id']}", json={"answer": "My edit."}, headers=alice)
        stats = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
        assert stats["kept"] == 30
        assert stats["more"]["sections"] > 0 and stats["more"]["pairs_to_generate"] > 0

        r = await client.post(f"/projects/{pid}/generate/more", headers=alice)
        assert r.status_code == 202, r.text

    state = await project(client, alice, pid)
    assert state["status"] == "in_review"
    after = (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()
    assert after["kept"] > 30
    pair = (await client.get(f"/projects/{pid}/pairs", params={"kept": True, "limit": 500}, headers=alice)).json()
    assert any(p["id"] == edited["id"] and p["answer"] == "My edit." for p in pair["items"])


async def test_generate_more_needs_review_state(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
    r = await client.post(f"/projects/{pid}/generate/more", headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "invalid_state"


def test_generation_prompt_lists_questions_to_avoid() -> None:
    from doctune.llm.prompts import StyleSpec, generation_messages

    spec = StyleSpec(description="d", tone="t", length="short", format="plain", language="en", examples=[])
    assert "already exist" not in generation_messages(spec, "text", 3)[0]["content"]
    prompt = generation_messages(spec, "text", 3, ["How do I reset it?"])[0]["content"]
    assert "already exist" in prompt and "- How do I reset it?" in prompt
