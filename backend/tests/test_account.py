from collections.abc import Callable

import httpx
import pytest
from fixtures import markdown_doc
from helpers import ALICE, BOB, create_project, upload
from sqlalchemy import func, select, update

from doctune.core.db import get_sessionmaker
from doctune.core.storage import get_storage
from doctune.models.generation import ProviderKey
from doctune.models.project import Project
from doctune.models.user import User

Auth = Callable[..., dict[str, str]]


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE, email="alice@example.com")


async def test_delete_account_removes_everything(client: httpx.AsyncClient, alice: dict[str, str], auth: Auth) -> None:
    from fake_llm import fake_groq

    pid = (await create_project(client, alice))["id"]
    await upload(client, alice, pid, "a.md", markdown_doc())
    with fake_groq():
        await client.put("/keys/groq", json={"api_key": "gsk_test_1234567890"}, headers=alice)
    bob_pid = (await create_project(client, auth(sub=BOB)))["id"]

    r = await client.delete("/me", headers=alice)
    assert r.status_code == 202
    async with get_sessionmaker()() as db:
        assert await db.get(User, ALICE) is None
        assert await db.scalar(select(func.count()).select_from(Project).where(Project.user_id == ALICE)) == 0
        assert await db.scalar(select(func.count()).select_from(ProviderKey)) == 0
        assert await db.get(Project, bob_pid) is not None  # other users untouched
    assert not (get_storage().root / f"u/{ALICE}").exists()  # type: ignore[attr-defined]


async def test_rate_limit(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    import redis

    r = redis.Redis.from_url("redis://localhost:56379/0")
    for key in r.scan_iter("api:rl:*"):
        r.delete(key)
    headers = {**alice, "x-test-rate-limit": "1"}
    codes = [
        (await client.post("/models/check", json={"hf_id": "not-valid"}, headers=headers)).status_code
        for _ in range(21)
    ]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429
    for key in r.scan_iter("api:rl:*"):
        r.delete(key)


async def test_admin_usage_is_admin_only(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    await client.get("/me", headers=alice)
    assert (await client.get("/admin/usage", headers=alice)).status_code == 404
    async with get_sessionmaker()() as db:
        await db.execute(update(User).values(is_admin=True))
        await db.commit()
    usage = (await client.get("/admin/usage", headers=alice)).json()
    assert usage["db_bytes"] > 0 and usage["users"] == 1
    assert set(usage["queue_depths"]) == {"parse", "llm", "embed", "default", "inference"}
