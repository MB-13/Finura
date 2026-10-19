from collections.abc import Callable

import httpx

Auth = Callable[..., dict[str, str]]


async def test_patch_me_updates_fields(client: httpx.AsyncClient, auth: Auth) -> None:
    headers = auth(sub="5d0f6c4e-4a5e-4f2b-9d55-3b2a2d6f1a10")
    r = await client.patch("/me", json={"display_name": "Alice", "onboarding_done": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["display_name"] == "Alice"
    assert r.json()["onboarding_done"] is True

    again = await client.get("/me", headers=headers)
    assert again.json()["display_name"] == "Alice"


async def test_patch_only_touches_sent_fields(client: httpx.AsyncClient, auth: Auth) -> None:
    headers = auth(sub="0b6f8b39-36d4-4b0e-a8a6-2b8b2f8c7c11")
    await client.patch("/me", json={"display_name": "Alice"}, headers=headers)
    r = await client.patch("/me", json={"email_notifications": False}, headers=headers)
    assert r.json()["display_name"] == "Alice"
    assert r.json()["email_notifications"] is False


async def test_validation_error_envelope(client: httpx.AsyncClient, auth: Auth) -> None:
    r = await client.patch("/me", json={"display_name": ""}, headers=auth())
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "display_name" in body["details"]["fields"]


async def test_users_only_see_themselves(client: httpx.AsyncClient, auth: Auth) -> None:
    alice = auth(sub="11111111-1111-4111-8111-111111111111", email="alice@example.com")
    bob = auth(sub="22222222-2222-4222-8222-222222222222", email="bob@example.com")
    await client.patch("/me", json={"display_name": "Alice"}, headers=alice)
    r = await client.get("/me", headers=bob)
    assert r.json()["email"] == "bob@example.com"
    assert r.json()["display_name"] is None
