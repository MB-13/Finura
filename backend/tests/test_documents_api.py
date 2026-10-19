from collections.abc import Callable

import httpx
import pytest
from fixtures import blank_pdf, docx_with_headings, markdown_doc, pdf_with_headings
from helpers import ALICE, create_project, local_path, upload

from doctune.core.config import get_settings
from doctune.core.storage import get_storage

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE)


async def project_state(client: httpx.AsyncClient, headers: dict[str, str], pid: str) -> dict[str, object]:
    return dict((await client.get(f"/projects/{pid}", headers=headers)).json())


async def test_upload_process_and_list_chunks(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await upload(client, alice, pid, "Guide.pdf", pdf_with_headings(sections=3))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "uploaded"
    state = await project_state(client, alice, pid)
    assert state["status"] == "uploaded"
    assert "process" in state["allowed_actions"]  # type: ignore[operator]

    r = await client.post(f"/projects/{pid}/process", headers=alice)
    assert r.status_code == 202
    # tasks run inline in tests, so parsing has finished by now
    state = await project_state(client, alice, pid)
    assert state["status"] == "awaiting_style"
    assert state["counts"]["chunks"] > 0  # type: ignore[index]

    docs = (await client.get(f"/projects/{pid}/documents", headers=alice)).json()
    assert docs[0]["status"] == "parsed"
    assert docs[0]["page_count"] == 3
    assert docs[0]["chunk_count"] == state["counts"]["chunks"]  # type: ignore[index]

    chunks = (await client.get(f"/projects/{pid}/chunks", headers=alice)).json()
    assert chunks["items"][0]["section_path"].startswith("Section 1")
    assert chunks["items"][0]["page_start"] == 1

    found = (await client.get(f"/projects/{pid}/chunks", params={"q": "section 3"}, headers=alice)).json()
    assert found["items"]

    activity = [e["to_status"] for e in (await client.get(f"/projects/{pid}/activity", headers=alice)).json()]
    assert activity[:3] == ["awaiting_style", "parsing", "uploaded"]


async def test_docx_and_markdown_are_supported(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    assert (await upload(client, alice, pid, "guide.docx", docx_with_headings())).status_code == 200
    assert (await upload(client, alice, pid, "handbook.md", markdown_doc())).status_code == 200
    await client.post(f"/projects/{pid}/process", headers=alice)
    chunks = (await client.get(f"/projects/{pid}/chunks", headers=alice)).json()["items"]
    paths = {c["section_path"] for c in chunks}
    assert any(p.startswith("User Guide") for p in paths)
    assert any(p.startswith("Handbook") for p in paths)


async def test_unsupported_extension(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/documents", json={"filename": "run.exe", "size_bytes": 10}, headers=alice)
    assert r.status_code == 415


async def test_file_disguised_as_pdf_is_rejected_and_removed(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await upload(client, alice, pid, "fake.pdf", b"<html>definitely not a pdf</html>")
    assert r.status_code == 415
    assert (await client.get(f"/projects/{pid}/documents", headers=alice)).json() == []
    assert (await project_state(client, alice, pid))["status"] == "draft"


async def test_size_limits(client: httpx.AsyncClient, alice: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    pid = (await create_project(client, alice))["id"]
    too_big = 21 * 1024 * 1024
    r = await client.post(
        f"/projects/{pid}/documents", json={"filename": "big.pdf", "size_bytes": too_big}, headers=alice
    )
    assert r.status_code == 413

    monkeypatch.setattr(get_settings(), "max_project_mb", 1)
    first = await client.post(
        f"/projects/{pid}/documents", json={"filename": "a.pdf", "size_bytes": 700_000}, headers=alice
    )
    assert first.status_code == 201
    second = await client.post(
        f"/projects/{pid}/documents", json={"filename": "b.pdf", "size_bytes": 700_000}, headers=alice
    )
    assert second.status_code == 413  # pending uploads count towards the project cap


async def test_upload_larger_than_declared_is_refused(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/documents", json={"filename": "a.pdf", "size_bytes": 10}, headers=alice)
    up = r.json()["upload"]
    put = await client.put(local_path(up["url"]), content=pdf_with_headings(1, 1), headers=up["headers"])
    assert put.status_code == 413


async def test_complete_before_upload(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/documents", json={"filename": "a.pdf", "size_bytes": 10}, headers=alice)
    doc_id = r.json()["document"]["id"]
    r = await client.post(f"/projects/{pid}/documents/{doc_id}/complete", headers=alice)
    assert r.status_code == 409
    assert r.json()["error"] == "upload_missing"


async def test_removing_last_document_returns_to_draft(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    doc = (await upload(client, alice, pid, "a.md", markdown_doc())).json()
    key = None
    r = await client.delete(f"/projects/{pid}/documents/{doc['id']}", headers=alice)
    assert r.status_code == 204
    state = await project_state(client, alice, pid)
    assert state["status"] == "draft"
    assert state["total_bytes"] == 0
    assert key is None


async def test_all_documents_unreadable_fails_project_with_retry(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    pid = (await create_project(client, alice))["id"]
    await upload(client, alice, pid, "blank.pdf", blank_pdf())
    await client.post(f"/projects/{pid}/process", headers=alice)
    state = await project_state(client, alice, pid)
    assert state["status"] == "failed"
    assert state["status_reason"] == "no_text"
    assert "retry" in state["allowed_actions"]  # type: ignore[operator]
    docs = (await client.get(f"/projects/{pid}/documents", headers=alice)).json()
    assert docs[0]["status"] == "failed"
    assert "No readable text" in docs[0]["error"]

    r = await client.post(f"/projects/{pid}/retry", headers=alice)
    assert r.json()["status"] == "uploaded"


async def test_adding_documents_after_parsing_goes_back_to_uploaded(
    client: httpx.AsyncClient, alice: dict[str, str]
) -> None:
    pid = (await create_project(client, alice))["id"]
    await upload(client, alice, pid, "a.md", markdown_doc())
    await client.post(f"/projects/{pid}/process", headers=alice)
    assert (await project_state(client, alice, pid))["status"] == "awaiting_style"
    await upload(client, alice, pid, "b.docx", docx_with_headings())
    assert (await project_state(client, alice, pid))["status"] == "uploaded"
    await client.post(f"/projects/{pid}/process", headers=alice)
    docs = (await client.get(f"/projects/{pid}/documents", headers=alice)).json()
    assert [d["status"] for d in docs] == ["parsed", "parsed"]


async def test_project_delete_removes_files(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    await upload(client, alice, pid, "a.md", markdown_doc())
    prefix_dir = get_storage().root / f"u/{ALICE}/p/{pid}"  # type: ignore[attr-defined]
    assert prefix_dir.exists()
    await client.delete(f"/projects/{pid}", headers=alice)
    assert not prefix_dir.exists()


async def test_chunks_have_embeddings(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    from sqlalchemy import func, select

    from doctune.core.db import get_sessionmaker
    from doctune.models.document import Chunk

    pid = (await create_project(client, alice))["id"]
    await upload(client, alice, pid, "a.md", markdown_doc())
    await client.post(f"/projects/{pid}/process", headers=alice)
    async with get_sessionmaker()() as db:
        missing = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None)))
    assert missing == 0
