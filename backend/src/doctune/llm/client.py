"""One OpenAI-compatible client over the user's own provider keys, with rate-limit fallback."""

import json
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import openai
import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from doctune.core.crypto import KeyDecryptError, decrypt
from doctune.llm.providers import PROVIDERS, ModelSpec
from doctune.llm.ratelimit import Budget, seconds_until_utc_midnight
from doctune.models.generation import KeyStatus, Provider, ProviderKey
from doctune.parsing.chunker import count_tokens

log = structlog.get_logger()

Message = dict[str, str]
MAX_INLINE_WAIT = 20.0  # wait up to this long in-process; longer waits pause the job instead
MAX_ROUNDS = 6


class LLMError(Exception):
    pass


class NoProviders(LLMError):
    """The user has no usable provider key."""


class ProvidersExhausted(LLMError):
    def __init__(self, retry_after: float):
        super().__init__(f"all providers rate-limited for {retry_after:.0f}s")
        self.retry_after = retry_after


class UpstreamError(LLMError):
    """Providers failed for reasons other than rate limits (timeouts, 5xx)."""


class BadModelOutput(LLMError):
    pass


@dataclass(frozen=True)
class Target:
    provider: Provider
    model: ModelSpec
    api_key: str
    key_id: uuid.UUID

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model.id}"


@dataclass
class LLMResult[T: BaseModel]:
    data: T
    target: Target
    tokens_in: int
    tokens_out: int


def build_chain(
    db: Session, user_id: uuid.UUID, preferred: tuple[str | None, str | None] = (None, None)
) -> list[Target]:
    """The user's usable (provider, model) pairs in fallback order."""
    keys = db.scalars(
        select(ProviderKey)
        .where(ProviderKey.user_id == user_id, ProviderKey.status != KeyStatus.invalid)
        .order_by(ProviderKey.priority, ProviderKey.created_at)
    ).all()
    chain: list[Target] = []
    for key in keys:
        spec = PROVIDERS.get(key.provider)
        if spec is None or (spec.requires_terms_ack and key.terms_acknowledged_at is None):
            continue
        try:
            secret = decrypt(key.ciphertext)
        except KeyDecryptError:
            log.error("key_decrypt_failed", provider=key.provider)
            continue
        models = list(spec.models)
        if key.default_model:
            models.sort(key=lambda m: m.id != key.default_model)
        chain.extend(Target(key.provider, m, secret, key.id) for m in models)
    want_provider, want_model = preferred
    if want_provider:
        chain.sort(key=lambda t: (t.provider != want_provider, bool(want_model) and t.model.id != want_model))
    return chain


_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:(\d+)ms)?")


def parse_duration(value: str | None) -> float | None:
    """Parse `retry-after` seconds or Groq-style `2m59.56s` / `450ms`."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    m = _DURATION_RE.fullmatch(value.strip())
    if not m or not any(m.groups()):
        return None
    h, mins, secs, ms = m.groups()
    return int(h or 0) * 3600 + int(mins or 0) * 60 + float(secs or 0) + int(ms or 0) / 1000


def _rate_limit_wait(exc: openai.RateLimitError) -> tuple[float, bool]:
    """(seconds to wait, is it a daily quota)."""
    text = str(exc).lower()
    daily = any(s in text for s in ("per day", "(rpd)", "(tpd)", "daily", "quota exceeded"))
    headers = exc.response.headers if exc.response is not None else {}
    wait = parse_duration(headers.get("retry-after"))
    if wait is None:
        resets = [parse_duration(headers.get(h)) for h in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens")]
        wait = max((r for r in resets if r is not None), default=None)
    if daily and (wait is None or wait < 60):
        wait = float(seconds_until_utc_midnight())
    return (wait if wait is not None else 30.0), daily


def _messages_tokens(messages: Sequence[Message]) -> int:
    return sum(count_tokens(m["content"]) + 4 for m in messages)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences and surrounding prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


ClientFactory = Callable[[Target], openai.OpenAI]


# Tests install a fake-provider transport here (httpx2 is the OpenAI SDK's HTTP library),
# so no test request can ever reach a real API.
test_transport: httpx2.BaseTransport | None = None


def default_client(target: Target) -> openai.OpenAI:
    http_client = httpx2.Client(transport=test_transport, timeout=60.0) if test_transport else None
    return openai.OpenAI(
        api_key=target.api_key,
        base_url=PROVIDERS[target.provider].base_url,
        timeout=60.0,
        max_retries=0,
        http_client=http_client,
    )


class LLMClient:
    def __init__(
        self,
        chain: list[Target],
        *,
        user_id: uuid.UUID,
        client_factory: ClientFactory = default_client,
        on_notice: Callable[[str], None] | None = None,
        on_key_invalid: Callable[[uuid.UUID], None] | None = None,
        on_key_quota: Callable[[uuid.UUID, datetime], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.chain = chain
        self.user_id = user_id
        self.client_factory = client_factory
        self.on_notice = on_notice or (lambda _msg: None)
        self.on_key_invalid = on_key_invalid or (lambda _id: None)
        self.on_key_quota = on_key_quota or (lambda _id, _until: None)
        self.sleep = sleep
        self._dead_keys: set[uuid.UUID] = set()

    def _call(self, target: Target, messages: list[Message], max_tokens: int, temperature: float) -> Any:
        kwargs: dict[str, Any] = {
            "model": target.model.id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if target.model.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self.client_factory(target).chat.completions.create(**kwargs)

    def complete_json[T: BaseModel](
        self,
        messages: list[Message],
        schema: type[T],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.4,
    ) -> LLMResult[T]:
        if not self.chain:
            raise NoProviders("Connect an API key in Settings to generate data.")
        estimate = _messages_tokens(messages) + max_tokens
        upstream_error: Exception | None = None
        bad_output = False
        last_wait: float | None = None

        for _round in range(MAX_ROUNDS):
            waits: list[float] = []
            usable = [t for t in self.chain if t.key_id not in self._dead_keys]
            if not usable:
                raise NoProviders("All your API keys were rejected. Check them in Settings.")
            for target in usable:
                if target.key_id in self._dead_keys:
                    continue
                budget = Budget(self.user_id, target.provider, target.model)
                if wait := budget.reserve(estimate):
                    waits.append(wait)
                    continue
                try:
                    resp = self._call(target, messages, max_tokens, temperature)
                except openai.RateLimitError as exc:
                    wait, daily = _rate_limit_wait(exc)
                    budget.cool_down(wait)
                    waits.append(wait)
                    if daily:
                        self.on_key_quota(target.key_id, datetime.now(UTC) + timedelta(seconds=wait))
                    self.on_notice(f"{target.label} hit its {'daily' if daily else 'rate'} limit; switching model.")
                    continue
                except (openai.AuthenticationError, openai.PermissionDeniedError):
                    self._dead_keys.add(target.key_id)
                    self.on_key_invalid(target.key_id)
                    self.on_notice(f"Your {PROVIDERS[target.provider].name} key was rejected.")
                    continue
                except (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError) as exc:
                    upstream_error = exc
                    continue
                except openai.APIStatusError as exc:
                    upstream_error = exc
                    continue

                usage = getattr(resp, "usage", None)
                tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
                tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
                if tokens_in or tokens_out:
                    budget.record_actual(estimate, tokens_in + tokens_out)
                content = resp.choices[0].message.content or ""
                parsed = self._parse(content, schema)
                if parsed is None:
                    # one repair attempt on the same model, then move on
                    repair = [
                        *messages,
                        {"role": "assistant", "content": content[:4000]},
                        {
                            "role": "user",
                            "content": "That was not valid JSON in the required format. "
                            "Reply with only the JSON object.",
                        },
                    ]
                    try:
                        resp2 = self._call(target, repair, max_tokens, temperature)
                        parsed = self._parse(resp2.choices[0].message.content or "", schema)
                    except openai.APIError:
                        parsed = None
                if parsed is None:
                    bad_output = True
                    continue
                return LLMResult(parsed, target, tokens_in, tokens_out)

            if all(t.key_id in self._dead_keys for t in self.chain):
                raise NoProviders("All your API keys were rejected. Check them in Settings.")
            if waits:
                shortest = min(waits)
                last_wait = shortest
                if shortest <= MAX_INLINE_WAIT:
                    self.sleep(shortest)
                    continue
                raise ProvidersExhausted(shortest)
            last_wait = None
            break
        if last_wait is not None and not bad_output:
            raise ProvidersExhausted(last_wait)
        if bad_output:
            raise BadModelOutput("The model did not return valid JSON.")
        raise UpstreamError(str(upstream_error) if upstream_error else "providers unavailable")

    @staticmethod
    def _parse[T: BaseModel](content: str, schema: type[T]) -> T | None:
        try:
            return schema.model_validate(extract_json(content))
        except (json.JSONDecodeError, ValidationError, ValueError):
            return None
