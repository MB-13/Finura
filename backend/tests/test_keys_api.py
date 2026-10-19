from collections.abc import Callable

import httpx
import pytest
from fake_llm import fake_groq
from helpers import ALICE, BOB
from sqlalchemy import select

from doctune.core.crypto import decrypt
from doctune.core.db import get_sessionmaker
from doctune.models.generation import ProviderKey

Auth = Callable[..., dict[str, str]]
SECRET = "gsk_live_abcdefghijklmnop1234"


@pytest.fixture
def alice(auth: Auth) -> dict[str, str]:
    return auth(sub=ALICE)


async def test_key_is_encrypted_masked_and_verified(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq():
        r = await client.put("/keys/groq", json={"api_key": SECRET}, headers=alice)
    assert r.status_code == 200
    assert r.json()["last4"] == "1234"
    assert SECRET not in r.text

    async with get_sessionmaker()() as db:
        row = await db.scalar(select(ProviderKey))
    assert row is not None
    assert SECRET.encode() not in row.ciphertext
    assert decrypt(row.ciphertext) == SECRET

    listed = await client.get("/keys", headers=alice)
    assert listed.json()[0]["status"] == "valid"  # verified inline (eager tasks) against the fake /models
    assert SECRET not in listed.text


async def test_rejected_key_is_marked_invalid(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq() as fake:
        fake.mode = "invalid_key"
        await client.put("/keys/groq", json={"api_key": SECRET}, headers=alice)
    assert (await client.get("/keys", headers=alice)).json()[0]["status"] == "invalid"


async def test_gemini_requires_terms(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    r = await client.put("/keys/gemini", json={"api_key": "AIza" + "x" * 30}, headers=alice)
    assert r.status_code == 409
    assert r.json()["error"] == "terms_required"


async def test_keys_are_per_user(client: httpx.AsyncClient, alice: dict[str, str], auth: Auth) -> None:
    with fake_groq():
        await client.put("/keys/groq", json={"api_key": SECRET}, headers=alice)
    assert (await client.get("/keys", headers=auth(sub=BOB))).json() == []


async def test_patch_and_delete(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    with fake_groq():
        await client.put("/keys/groq", json={"api_key": SECRET}, headers=alice)
    r = await client.patch("/keys/groq", json={"priority": 3, "default_model": "openai/gpt-oss-20b"}, headers=alice)
    assert r.json()["priority"] == 3
    assert (await client.delete("/keys/groq", headers=alice)).status_code == 204
    assert (await client.delete("/keys/groq", headers=alice)).status_code == 404


async def test_providers_catalog(client: httpx.AsyncClient, alice: dict[str, str]) -> None:
    providers = {p["provider"]: p for p in (await client.get("/providers", headers=alice)).json()}
    assert providers["gemini"]["requires_terms_ack"] is True
    assert providers["groq"]["models"][0]["id"] == "openai/gpt-oss-120b"
