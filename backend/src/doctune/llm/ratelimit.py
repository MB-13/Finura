"""Per-user, per-(provider, model) budget tracking in Redis.

Minute windows for requests/tokens, UTC-day windows for daily caps, plus explicit cool-downs learned
from provider 429 responses. Counters are approximate (no cross-key atomicity) — good enough to stay
under free tiers; the provider's own 429 is the final word and feeds back via `cool_down`.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import redis

from doctune.core.config import get_settings
from doctune.llm.providers import ModelSpec


@lru_cache
def _redis() -> "redis.Redis":
    return redis.Redis.from_url(get_settings().redis_url)


def _key(kind: str, user_id: uuid.UUID, provider: str, model: str, window: int | str) -> str:
    return f"rl:{kind}:{user_id}:{provider}:{model}:{window}"


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return int((tomorrow - now).total_seconds())


@dataclass
class Budget:
    user_id: uuid.UUID
    provider: str
    model: ModelSpec

    def cooldown_left(self) -> float:
        until: bytes | None = _redis().get(_key("cool", self.user_id, self.provider, self.model.id, "x"))  # type: ignore[assignment]
        return max(0.0, float(until) - time.time()) if until else 0.0

    def cool_down(self, seconds: float) -> None:
        until = time.time() + seconds
        _redis().set(_key("cool", self.user_id, self.provider, self.model.id, "x"), until, ex=int(seconds) + 5)

    def reserve(self, tokens: int) -> float:
        """Try to reserve one request of ~`tokens`. Returns 0 if reserved, else seconds to wait."""
        if (left := self.cooldown_left()) > 0:
            return left
        r = _redis()
        now = time.time()
        minute = int(now // 60)
        day = datetime.now(UTC).strftime("%Y%m%d")
        m = self.model
        rk, tk = (_key(k, self.user_id, self.provider, m.id, minute) for k in ("rpm", "tpm"))
        dk, dtk = (_key(k, self.user_id, self.provider, m.id, day) for k in ("rpd", "tpd"))

        pipe = r.pipeline()
        pipe.incr(rk)
        pipe.incrby(tk, tokens)
        pipe.incr(dk)
        pipe.incrby(dtk, tokens)
        pipe.expire(rk, 120)
        pipe.expire(tk, 120)
        pipe.expire(dk, 90_000)
        pipe.expire(dtk, 90_000)
        reqs, toks, dreqs, dtoks, *_ = pipe.execute()

        wait = 0.0
        if (m.rpd and dreqs > m.rpd) or (m.tpd and dtoks > m.tpd):
            wait = seconds_until_utc_midnight()
        elif reqs > m.rpm or toks > m.tpm:
            wait = 60 - (now % 60) + 0.5
        if wait:
            undo = r.pipeline()
            undo.decr(rk)
            undo.decrby(tk, tokens)
            undo.decr(dk)
            undo.decrby(dtk, tokens)
            undo.execute()
        return wait

    def record_actual(self, estimated: int, actual: int) -> None:
        """Correct the token counters once the provider reports real usage."""
        delta = actual - estimated
        if delta:
            minute = int(time.time() // 60)
            day = datetime.now(UTC).strftime("%Y%m%d")
            r = _redis()
            r.incrby(_key("tpm", self.user_id, self.provider, self.model.id, minute), delta)
            r.incrby(_key("tpd", self.user_id, self.provider, self.model.id, day), delta)
