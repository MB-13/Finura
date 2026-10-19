import time
import uuid

import pytest
from fake_llm import fake_groq
from pydantic import BaseModel

from doctune.llm.client import (
    BadModelOutput,
    LLMClient,
    NoProviders,
    ProvidersExhausted,
    Target,
    extract_json,
    parse_duration,
)
from doctune.llm.providers import PROVIDERS, ModelSpec
from doctune.llm.ratelimit import Budget
from doctune.models.generation import Provider


class Out(BaseModel):
    pairs: list[dict[str, str]]


MSG = [{"role": "user", "content": "Write 2 new question-answer pairs based ONLY on the source text."}]
KEY_ID = uuid.uuid4()


def chain() -> list[Target]:
    return [Target(Provider.groq, m, "gsk_test", KEY_ID) for m in PROVIDERS[Provider.groq].models]


def client(**kw: object) -> LLMClient:
    kw.setdefault("sleep", lambda _s: None)
    return LLMClient(chain(), user_id=uuid.uuid4(), **kw)  # type: ignore[arg-type]


def test_success_returns_validated_json() -> None:
    with fake_groq() as fake:
        result = client().complete_json(MSG, Out)
    assert len(result.data.pairs) == 2
    assert result.target.model.id == "openai/gpt-oss-120b"
    assert result.tokens_in == 100
    assert fake.calls[0]["model"] == "openai/gpt-oss-120b"


def test_rate_limited_model_falls_back_to_next_model() -> None:
    notices: list[str] = []
    with fake_groq() as fake:
        fake.bad_models = {"openai/gpt-oss-120b"}
        result = client(on_notice=notices.append).complete_json(MSG, Out)
    assert result.target.model.id == "qwen/qwen3.8-27b"
    assert any("rate limit" in n for n in notices)


def test_daily_quota_marks_key_and_moves_on() -> None:
    quota: list[uuid.UUID] = []
    with fake_groq() as fake:
        fake.mode = "daily_quota"
        with pytest.raises(ProvidersExhausted) as exc:
            client(on_key_quota=lambda kid, _until: quota.append(kid)).complete_json(MSG, Out)
    assert exc.value.retry_after >= 60
    assert quota == [KEY_ID, KEY_ID, KEY_ID]
    assert len(fake.calls) == 3  # each model tried once


def test_short_rate_limits_wait_inline_then_succeed() -> None:
    slept: list[float] = []
    with fake_groq() as fake:
        fake.mode = "rate_limit"
        c = client(sleep=lambda s: (slept.append(s), setattr(fake, "mode", "ok"), time.sleep(s)))
        result = c.complete_json(MSG, Out)
    assert slept and slept[0] <= 20
    assert result.data.pairs


def test_invalid_key_is_reported_and_raises_when_none_left() -> None:
    invalid: list[uuid.UUID] = []
    with fake_groq() as fake:
        fake.mode = "invalid_key"
        with pytest.raises(NoProviders):
            client(on_key_invalid=invalid.append).complete_json(MSG, Out)
    assert invalid == [KEY_ID]
    assert len(fake.calls) == 1  # the dead key isn't retried on other models


def test_broken_json_is_repaired_once() -> None:
    with fake_groq() as fake:
        fake.broken_once = True
        result = client().complete_json(MSG, Out)
    assert result.data.pairs
    assert len(fake.calls) == 2


def test_always_broken_json_raises() -> None:
    with fake_groq() as fake:
        fake.mode = "broken_json"
        with pytest.raises(BadModelOutput):
            client().complete_json(MSG, Out)


def test_no_keys() -> None:
    with pytest.raises(NoProviders):
        LLMClient([], user_id=uuid.uuid4()).complete_json(MSG, Out)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12", 12.0), ("1.5", 1.5), ("2m59.5s", 179.5), ("450ms", 0.45), ("1h", 3600.0), (None, None), ("soon", None)],
)
def test_parse_duration(value: str | None, expected: float | None) -> None:
    assert parse_duration(value) == expected


def test_extract_json_tolerates_fences_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_budget_blocks_after_rpm_and_cooldown() -> None:
    budget = Budget(uuid.uuid4(), "groq", ModelSpec("tiny", rpm=1, tpm=1_000))
    assert budget.reserve(10) == 0
    assert budget.reserve(10) > 0  # second request in the same minute
    other = Budget(uuid.uuid4(), "groq", ModelSpec("tiny", rpm=5, tpm=1_000))
    other.cool_down(30)
    assert 0 < other.reserve(10) <= 30
