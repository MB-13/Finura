from collections.abc import Callable

import httpx
import pytest
from helpers import ALICE, BOB, create_project

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


@pytest.fixture
def bob(auth: Auth) -> dict[str, str]:
    return auth(sub=BOB, email="bob@example.com")


async def test_create_and_get_project(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    project = await create_project(client, alice, "Support bot")
    assert project["status"] == "draft"
    assert project["target_pairs"] == 500
    assert project["counts"]["documents"] == 0
    assert "upload" in project["allowed_actions"]
    assert "process" not in project["allowed_actions"]

    r = await client.get(f"/projects/{project['id']}", headers=alice)
    assert r.status_code == 200
    assert r.json()["name"] == "Support bot"


async def test_other_users_get_404_everywhere(
    client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    pid = (await create_project(client, alice))["id"]
    for method, path, body in [
        ("GET", f"/projects/{pid}", None),
        ("PATCH", f"/projects/{pid}", {"name": "x"}),
        ("DELETE", f"/projects/{pid}", None),
        ("POST", f"/projects/{pid}/process", None),
        ("POST", f"/projects/{pid}/retry", None),
        ("GET", f"/projects/{pid}/activity", None),
        ("GET", f"/projects/{pid}/documents", None),
        ("POST", f"/projects/{pid}/documents", {"filename": "a.pdf", "size_bytes": 10}),
        ("GET", f"/projects/{pid}/chunks", None),
        ("GET", f"/projects/{pid}/events", None),
    ]:
        r = await client.request(method, path, json=body, headers=bob)
        assert r.status_code == 404, (method, path, r.status_code)


async def test_list_is_scoped_and_paginated(
    client: httpx.AsyncClient, alice: dict[str, str], bob: dict[str, str]
) -> None:
    for i in range(3):
        await create_project(client, alice, f"p{i}")
    await create_project(client, bob, "bob's")

    r = await client.get("/projects", params={"limit": 2}, headers=alice)
    page1 = r.json()
    assert [p["name"] for p in page1["items"]] == ["p2", "p1"]
    assert page1["next_cursor"]
    r = await client.get("/projects", params={"limit": 2, "cursor": page1["next_cursor"]}, headers=alice)
    assert [p["name"] for p in r.json()["items"]] == ["p0"]
    assert r.json()["next_cursor"] is None


async def test_patch_validates(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.patch(f"/projects/{pid}", json={"name": "Renamed", "target_pairs": 1000}, headers=alice)
    assert r.json()["name"] == "Renamed"
    assert r.json()["target_pairs"] == 1000
    r = await client.patch(f"/projects/{pid}", json={"target_pairs": 5000}, headers=alice)
    assert r.status_code == 422
    r = await client.patch(f"/projects/{pid}", json={"name": ""}, headers=alice)
    assert r.status_code == 422


async def test_project_limit(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    for i in range(20):
        await create_project(client, alice, f"p{i}")
    r = await client.post("/projects", json={"name": "one too many"}, headers=alice)
    assert r.status_code == 413
    assert r.json()["error"] == "limit_exceeded"


async def test_delete_purges_project(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.delete(f"/projects/{pid}", headers=alice)
    assert r.status_code == 202
    assert (await client.get(f"/projects/{pid}", headers=alice)).status_code == 404
    assert (await client.get("/projects", headers=alice)).json()["items"] == []


async def test_process_without_documents_is_rejected(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/process", headers=alice)
    assert r.status_code == 409


async def test_retry_only_when_failed(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.post(f"/projects/{pid}/retry", headers=alice)
    assert r.status_code == 409


async def test_activity_records_creation(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    events = (await client.get(f"/projects/{pid}/activity", headers=alice)).json()
    assert events[0]["type"] == "created"


async def test_patch_generation_provider(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    pid = (await create_project(client, alice))["id"]
    r = await client.patch(
        f"/projects/{pid}", json={"gen_provider": "groq", "gen_model": "openai/gpt-oss-20b"}, headers=alice
    )
    assert r.json()["gen_provider"] == "groq"
    assert r.json()["gen_model"] == "openai/gpt-oss-20b"
    assert (await client.patch(f"/projects/{pid}", json={"gen_provider": "openai"}, headers=alice)).status_code == 422
