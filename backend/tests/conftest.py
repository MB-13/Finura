"""Test setup: a dedicated `doctune_test` database, a static JWKS for signing test tokens, temp storage.

Environment variables are set before any `doctune` import so the cached settings pick them up.
"""

import json
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

PG = os.environ.get("TEST_PG", "doctune:doctune@localhost:55432")  # user:password@host:port
PG_ADMIN_URL = f"postgresql://{PG}/postgres"
TEST_DB = "doctune_test"
SUPABASE_URL = "http://supabase.test"
KID = "test-key-1"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_jwk = json.loads(RSAAlgorithm.to_jwk(_private_key.public_key()))
_public_jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})

os.environ.update(
    {
        "ENV": "test",
        "DATABASE_URL": f"postgresql+asyncpg://{PG}/{TEST_DB}",
        "DATABASE_URL_SYNC": f"postgresql+psycopg://{PG}/{TEST_DB}",
        "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:56379/0"),
        "SUPABASE_URL": SUPABASE_URL,
        "JWT_JWKS_JSON": json.dumps({"keys": [_public_jwk]}),
        "STORAGE_LOCAL_DIR": tempfile.mkdtemp(prefix="doctune-storage-"),
        "STORAGE_SIGNING_KEY": "test-signing-key",
        "EMAIL_BACKEND": "console",
        "LLAMA_MODELS_DIR": tempfile.mkdtemp(prefix="doctune-models-"),
        "PUBLIC_API_URL": "http://testserver",
        "EMBEDDING_BACKEND": "hash",
    }
)
os.environ.pop("SUPABASE_JWT_SECRET", None)

import httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from doctune.core.db import get_engine  # noqa: E402
from doctune.main import create_app  # noqa: E402
from doctune.workers.celery_app import app as celery_app  # noqa: E402

# run Celery tasks inline so API tests exercise the real worker code
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.attributes["url"] = os.environ["DATABASE_URL_SYNC"]
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    yield
    async with get_engine().begin() as conn:
        await conn.execute(text("TRUNCATE users, email_log, projects CASCADE"))


@pytest.fixture(autouse=True)
def no_real_provider_calls() -> Iterator[None]:
    """Outside `fake_groq()`, any provider call fails instead of reaching the internet."""
    import httpx2 as httpx

    from doctune.llm import client as llm_client

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"test tried to call a real provider: {request.url}")

    llm_client.test_transport = httpx.MockTransport(refuse)
    import httpx as plain_httpx

    from doctune.training import hf_check

    def refuse_hf(request: plain_httpx.Request) -> plain_httpx.Response:
        raise AssertionError(f"test tried to call Hugging Face: {request.url}")

    hf_check.test_transport = plain_httpx.MockTransport(refuse_hf)

    from doctune.workers.tasks import models as model_tasks

    def refuse_download(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("test tried to download base model files")

    original_fetch = model_tasks.fetch_base_config
    model_tasks.fetch_base_config = refuse_download
    yield
    model_tasks.fetch_base_config = original_fetch
    llm_client.test_transport = None
    hf_check.test_transport = None


@pytest.fixture(autouse=True)
def no_real_kaggle_calls() -> Iterator[None]:
    """Outside the `kaggle` fixture (tests/fake_kaggle.py), any Kaggle call fails instead of reaching the internet."""
    import httpx as plain_httpx

    from doctune.training import kaggle_client

    def refuse(request: plain_httpx.Request) -> plain_httpx.Response:
        raise AssertionError(f"test tried to call Kaggle: {request.url}")

    kaggle_client.test_transport = plain_httpx.MockTransport(refuse)
    yield
    kaggle_client.test_transport = None


@pytest.fixture(autouse=True)
def clear_rate_limits() -> Iterator[None]:
    """Rate-limit counters live in Redis; tests must not inherit each other's budgets."""
    import redis

    r = redis.Redis.from_url(os.environ["REDIS_URL"])
    for key in r.scan_iter("rl:*"):
        r.delete(key)
    yield


@pytest.fixture(scope="session")
def app() -> Any:
    return create_app()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


TokenFactory = Callable[..., str]


@pytest.fixture
def make_token() -> TokenFactory:
    def _make(
        sub: str | None = None,
        email: str | None = "alice@example.com",
        expires_in: int = 3600,
        aud: str = "authenticated",
        iss: str = f"{SUPABASE_URL}/auth/v1",
        kid: str = KID,
        **extra: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "sub": sub or str(uuid.uuid4()),
            "email": email,
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + expires_in,
            "role": "authenticated",
            **extra,
        }
        return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": kid})

    return _make


@pytest.fixture
def auth(make_token: TokenFactory) -> Callable[..., dict[str, str]]:
    def _auth(**kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(**kwargs)}"}

    return _auth
