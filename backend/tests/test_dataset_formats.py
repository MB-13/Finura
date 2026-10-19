"""Dataset formats (ADR-0003): the chosen format drives generation, judging, review, approval and export."""

import json
from collections.abc import Callable

import httpx
import pytest
from fake_llm import fake_groq
from helpers import ALICE
from test_generation_flow import STYLE, project, ready_project

from doctune.core.db import get_sessionmaker
from doctune.core.storage import get_storage
from doctune.llm.prompts import StyleSpec, judge_messages
from doctune.models.generation import DatasetVersion
from doctune.services import formats
from doctune.services.style import StyleIn, content_hash

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


async def generated(client: httpx.AsyncClient, alice: dict[str, str], dataset_format: str) -> str:
    """A project in review whose dataset was generated in `dataset_format`."""
    with fake_groq() as fake:
        pid = await ready_project(client, alice, fake)
        r = await client.put(f"/projects/{pid}/style", json={**STYLE, "dataset_format": dataset_format}, headers=alice)
        assert r.status_code == 200 and r.json()["dataset_format"] == dataset_format
        r = await client.post(f"/projects/{pid}/preview", json={"n_chunks": 2, "pairs_per_chunk": 2}, headers=alice)
        assert r.status_code == 202, r.text
        r = await client.post(f"/projects/{pid}/generate", json={"confirm": True}, headers=alice)
        assert r.status_code == 202, r.text
    state = await project(client, alice, pid)
    assert state["status"] == "in_review", state
    return pid


async def kept_pairs(client: httpx.AsyncClient, alice: dict[str, str], pid: str) -> list[dict[str, object]]:
    r = await client.get(f"/projects/{pid}/pairs", params={"kept": True, "limit": 500}, headers=alice)
    return list(r.json()["items"])


async def approved_lines(client: httpx.AsyncClient, alice: dict[str, str], pid: str) -> list[dict[str, object]]:
    r = await client.post(f"/projects/{pid}/dataset/approve", json={"allow_small": True}, headers=alice)
    assert r.status_code == 200, r.text
    async with get_sessionmaker()() as db:
        row = await db.get(DatasetVersion, r.json()["id"])
    assert row is not None and row.dataset_format == r.json()["dataset_format"]
    text = get_storage().read_bytes(row.train_key).decode() + get_storage().read_bytes(row.eval_key).decode()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def test_formats_are_listed(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    listed = (await client.get("/dataset-formats", headers=alice)).json()
    assert [f["key"] for f in listed] == ["qa_chat", "instruction", "multi_turn"]
    assert all(f["sample"]["format"] == f["key"] for f in listed)


async def test_instruction_dataset_trains_as_chat_and_exports_as_alpaca(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    pid = await generated(client, alice, "instruction")
    pairs = await kept_pairs(client, alice, pid)
    assert len(pairs) == 50
    assert all(p["dataset_format"] == "instruction" for p in pairs)
    with_input = next(p for p in pairs if p["record"]["input"])  # type: ignore[index]
    assert with_input["question"] == with_input["record"]["instruction"]  # type: ignore[index]

    # editing the whole example; a record in another format is refused
    edited = {"format": "instruction", "instruction": "Rewrite it.", "input": "Some text.", "output": "New."}
    r = await client.patch(f"/projects/{pid}/pairs/{with_input['id']}", json={"record": edited}, headers=alice)
    assert r.status_code == 200 and r.json()["record"] == edited and r.json()["edited"] is True
    wrong = {"format": "qa_chat", "question": "Why?", "answer": "Because."}
    r = await client.patch(f"/projects/{pid}/pairs/{with_input['id']}", json={"record": wrong}, headers=alice)
    assert r.status_code == 409 and r.json()["error"] == "format_mismatch"

    # a plain question + answer becomes an instruction without input
    r = await client.post(f"/projects/{pid}/pairs", json={"question": "Do X?", "answer": "Yes."}, headers=alice)
    assert r.json()["record"] == {"format": "instruction", "instruction": "Do X?", "input": "", "output": "Yes."}

    lines = await approved_lines(client, alice, pid)
    users = [line["messages"][0]["content"] for line in lines]  # type: ignore[index]
    assert "Rewrite it.\n\nSome text." in users

    native = (await client.post(f"/projects/{pid}/dataset/export", json={"shape": "native"}, headers=alice)).json()
    key = native["url"].split("/storage/", 1)[1].split("?", 1)[0]
    first = json.loads(get_storage().read_bytes(key).decode().splitlines()[0])
    assert set(first) == {"instruction", "input", "output"}


async def test_conversation_dataset_keeps_every_turn(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = await generated(client, alice, "multi_turn")
    pairs = await kept_pairs(client, alice, pid)
    assert pairs and all(len(p["record"]["messages"]) == 4 for p in pairs)  # type: ignore[index]
    # conversations are capped at 3 per section (10 sections here); the malformed one the fake adds to every
    # response was skipped on its own, not the whole response
    assert (await client.get(f"/projects/{pid}/dataset/stats", headers=alice)).json()["kept"] == 30
    est = (await client.get(f"/projects/{pid}/estimate", headers=alice)).json()
    assert (est["pairs_per_chunk"], est["supported_pairs"]) == (3, 30)

    bad = {
        "format": "multi_turn",
        "messages": [{"role": "assistant", "content": "Hi"}, {"role": "user", "content": "?"}],
    }
    r = await client.patch(f"/projects/{pid}/pairs/{pairs[0]['id']}", json={"record": bad}, headers=alice)
    assert r.status_code == 422

    lines = await approved_lines(client, alice, pid)
    assert [m["role"] for m in lines[0]["messages"]] == ["user", "assistant", "user", "assistant"]  # type: ignore[index]

    native = (await client.post(f"/projects/{pid}/dataset/export", json={"shape": "native"}, headers=alice)).json()
    key = native["url"].split("/storage/", 1)[1].split("?", 1)[0]
    first = json.loads(get_storage().read_bytes(key).decode().splitlines()[0])
    assert [t["from"] for t in first["conversations"]] == ["human", "gpt", "human", "gpt"]


async def test_restyling_to_another_format_reshapes_user_pairs(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    pid = await generated(client, alice, "multi_turn")
    single = {
        "format": "multi_turn",
        "messages": [{"role": "user", "content": "Q one?"}, {"role": "assistant", "content": "A."}],
    }
    longer = {
        "format": "multi_turn",
        "messages": [
            {"role": "user", "content": "Q two?"},
            {"role": "assistant", "content": "A."},
            {"role": "user", "content": "More?"},
            {"role": "assistant", "content": "B."},
        ],
    }
    for rec in (single, longer):
        assert (await client.post(f"/projects/{pid}/pairs", json={"record": rec}, headers=alice)).status_code == 201
    await client.post(f"/projects/{pid}/dataset/restyle", headers=alice)
    r = await client.put(f"/projects/{pid}/style", json={**STYLE, "dataset_format": "qa_chat"}, headers=alice)
    assert r.status_code == 200

    rows = (await client.get(f"/projects/{pid}/pairs", params={"limit": 500}, headers=alice)).json()["items"]
    by_q = {p["question"]: p for p in rows}
    assert by_q["Q one?"]["record"] == {"format": "qa_chat", "question": "Q one?", "answer": "A."}
    assert by_q["Q one?"]["kept"] is True
    # a real conversation can't become one question; it is set aside unchanged and comes back with the format
    assert by_q["Q two?"]["kept"] is False and by_q["Q two?"]["dropped_reason"] == "format_changed"
    assert by_q["Q two?"]["dataset_format"] == "multi_turn"
    await client.put(f"/projects/{pid}/style", json={**STYLE, "dataset_format": "multi_turn"}, headers=alice)
    rows = (await client.get(f"/projects/{pid}/pairs", params={"limit": 500}, headers=alice)).json()["items"]
    assert {p["question"]: p["kept"] for p in rows} == {"Q one?": True, "Q two?": True}


def test_existing_styles_keep_their_hash() -> None:
    style = StyleIn.model_validate(STYLE)
    assert content_hash(style) == content_hash(style.model_copy(update={"dataset_format": "qa_chat"}))
    assert content_hash(style) != content_hash(style.model_copy(update={"dataset_format": "instruction"}))


def test_qa_judge_prompt_is_unchanged_and_conversations_score_the_weakest_turn() -> None:
    spec = StyleSpec("A friendly bot.", "friendly", "short", "plain", "en", [{"input": "q", "output": "a"}])
    text = formats.judge_text("qa_chat", "Why?", "Because.", None)
    prompt = judge_messages(spec, "chunk", [{"id": "p1", "text": text}])[0]["content"]
    assert "[p1]\nQ: Why?\nA: Because.\n" in prompt
    assert "5 = fully supported by the source text, 1 = contradicts it or invents facts" in prompt
    spec.dataset_format = "multi_turn"
    assert "WEAKEST assistant turn" in judge_messages(spec, "chunk", [])[0]["content"]


def test_records_round_trip_through_columns() -> None:
    conv = formats.ConversationRecord.model_validate(formats.FORMATS["multi_turn"].sample.model_dump())
    q, a, record = formats.columns(conv)
    assert formats.view("multi_turn", q, a, record) == conv
    instr = formats.InstructionRecord(instruction="Do it.", output="Done.")
    assert formats.columns(instr) == ("Do it.", "Done.", None)
    assert formats.convert("multi_turn", q, a, record, "qa_chat") is None
