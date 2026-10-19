"""Fixed-window request limits in Redis, used as FastAPI dependencies on costly endpoints."""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from redis.asyncio import Redis

from doctune.core.config import get_settings
from doctune.core.errors import RateLimited


def limit(name: str, per_minute: int) -> Callable[[Request], Awaitable[None]]:
    """Limit by the caller's bearer token (user or job) or, without one, by client IP."""

    async def dependency(request: Request) -> None:
        if get_settings().env == "test" and not request.headers.get("x-test-rate-limit"):
            return
        auth = request.headers.get("authorization", "")
        who = auth[-24:] if auth else (request.client.host if request.client else "anon")
        window = int(time.time() // 60)
        key = f"api:rl:{name}:{who}:{window}"
        client = Redis.from_url(get_settings().redis_url)
        async with client:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 90)
        if count > per_minute:
            raise RateLimited(f"Too many requests. Try again in {60 - int(time.time()) % 60}s.")

    return dependency
