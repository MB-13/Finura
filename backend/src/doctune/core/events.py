"""Project events over Redis pub/sub; the SSE endpoint relays them to the browser."""

import json
import uuid
from functools import lru_cache
from typing import Any

import redis

from doctune.core.config import get_settings


def channel(project_id: uuid.UUID | str) -> str:
    return f"proj:{project_id}"


@lru_cache
def _sync_client() -> "redis.Redis":
    return redis.Redis.from_url(get_settings().redis_url)


def publish(project_id: uuid.UUID | str, type_: str, data: dict[str, Any]) -> None:
    """Publish from API or worker code. Best effort: events are hints; clients re-fetch on reconnect."""
    payload = json.dumps({"type": type_, "data": data}, default=str)
    _sync_client().publish(channel(project_id), payload)
