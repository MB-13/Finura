import uuid
from datetime import UTC, datetime

import openai
import structlog
from sqlalchemy import select

from doctune.core.crypto import KeyDecryptError, decrypt
from doctune.core.db import sync_session
from doctune.llm.client import Target, default_client
from doctune.llm.providers import PROVIDERS
from doctune.models.generation import KeyStatus, Provider, ProviderKey
from doctune.workers.celery_app import app

log = structlog.get_logger()


@app.task(name="doctune.workers.tasks.keys.verify_key", soft_time_limit=60)
def verify_key(user_id: str, provider: str) -> str:
    """Check a key by listing models (free, no tokens). Network trouble leaves it `unverified`."""
    p = Provider(provider)
    with sync_session() as db:
        key = db.scalar(select(ProviderKey).where(ProviderKey.user_id == uuid.UUID(user_id), ProviderKey.provider == p))
        if key is None:
            return "missing"
        try:
            secret = decrypt(key.ciphertext)
        except KeyDecryptError:
            key.status = KeyStatus.invalid
            db.commit()
            return key.status
        target = Target(p, PROVIDERS[p].models[0], secret, key.id)
        try:
            default_client(target).models.list()
            key.status = KeyStatus.valid
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            key.status = KeyStatus.invalid
        except openai.RateLimitError:
            key.status = KeyStatus.valid  # rate-limited means the key itself works
        except openai.APIError as exc:
            log.warning("key_verify_inconclusive", provider=provider, error=type(exc).__name__)
            return key.status
        key.last_verified_at = datetime.now(UTC)
        db.commit()
        return key.status
