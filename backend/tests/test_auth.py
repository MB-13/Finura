import base64
import json
import uuid

import httpx
import jwt
import pytest
from conftest import TokenFactory
from pydantic import SecretStr


async def test_missing_token_is_401_with_error_envelope(client: httpx.AsyncClient) -> None:
    r = await client.get("/me")
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized", "message": "Authentication required"}


async def test_non_bearer_scheme_is_401(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    r = await client.get("/me", headers={"Authorization": f"Basic {make_token()}"})
    assert r.status_code == 401


async def test_valid_token_creates_user_on_first_request(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    sub = str(uuid.uuid4())
    r = await client.get("/me", headers={"Authorization": f"Bearer {make_token(sub=sub, email='bob@example.com')}"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == sub
    assert body["email"] == "bob@example.com"
    assert body["onboarding_done"] is False


async def test_email_follows_supabase(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    sub = str(uuid.uuid4())
    await client.get("/me", headers={"Authorization": f"Bearer {make_token(sub=sub, email='old@example.com')}"})
    r = await client.get("/me", headers={"Authorization": f"Bearer {make_token(sub=sub, email='new@example.com')}"})
    assert r.json()["email"] == "new@example.com"


async def test_expired_token(client: httpx.AsyncClient, make_token: TokenFactory) -> None:
    r = await client.get("/me", headers={"Authorization": f"Bearer {make_token(expires_in=-10)}"})
    assert r.status_code == 401
    assert r.json()["error"] == "token_expired"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"aud": "anon"},
        {"iss": "http://evil.example/auth/v1"},
        {"kid": "unknown-key"},
        {"sub": "not-a-uuid"},
    ],
)
async def test_rejected_claims(client: httpx.AsyncClient, make_token: TokenFactory, kwargs: dict[str, str]) -> None:
    r = await client.get("/me", headers={"Authorization": f"Bearer {make_token(**kwargs)}"})
    assert r.status_code == 401


async def test_alg_none_is_rejected(client: httpx.AsyncClient) -> None:
    def b64(d: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': str(uuid.uuid4()), 'aud': 'authenticated'})}."
    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_hs256_rejected_when_no_secret_configured_with_a_hint(client: httpx.AsyncClient) -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated", "exp": 9999999999}, "x" * 32, algorithm="HS256"
    )
    r = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "SUPABASE_JWT_SECRET" in r.json()["message"]  # local/test explain the fix


async def test_garbage_token(client: httpx.AsyncClient) -> None:
    r = await client.get("/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_production_hides_configuration_hints() -> None:
    from doctune.core.auth import TokenVerifier
    from doctune.core.config import get_settings

    prod = get_settings().model_copy(update={"env": "prod"})
    assert TokenVerifier(prod)._explain("details") == "Unsupported token"


def test_signing_keys_and_legacy_secret_work_together() -> None:
    """A project mid-migration issues both kinds of token; with the secret set, JWKS must still be used."""
    import time
    import uuid as _uuid

    from conftest import KID, SUPABASE_URL, _private_key  # type: ignore[attr-defined]

    from doctune.core.auth import TokenVerifier
    from doctune.core.config import get_settings

    settings = get_settings().model_copy(update={"supabase_jwt_secret": SecretStr("s" * 40)})
    verifier = TokenVerifier(settings)
    now = int(time.time())
    claims = {"sub": str(_uuid.uuid4()), "aud": "authenticated", "iss": f"{SUPABASE_URL}/auth/v1", "exp": now + 60}
    rs = jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": KID})
    hs = jwt.encode(claims, "s" * 40, algorithm="HS256")
    assert verifier.verify(rs)["sub"] == claims["sub"]
    assert verifier.verify(hs)["sub"] == claims["sub"]
