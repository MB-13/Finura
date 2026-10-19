"""A fake OpenAI-compatible provider (Groq URL) for tests, served through an httpx MockTransport."""

import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx

from doctune.llm import client as llm_client

GROQ = "https://api.groq.com/openai/v1"


@dataclass
class FakeProvider:
    """Behaviour switches; tests flip them between calls."""

    mode: str = "ok"  # ok | rate_limit | daily_quota | invalid_key | broken_json | server_error
    bad_models: set[str] = field(default_factory=set)  # models that answer 429 even in ok mode
    judge_scores: tuple[int, int] = (5, 5)
    low_score_every: int = 0  # every Nth judged pair gets 2/2
    broken_once: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)
    _judged: int = 0

    def reply(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        model = body["model"]
        prompt = body["messages"][0]["content"]
        self.calls.append({"model": model, "kind": "judge" if "reviewing training data" in prompt else "generate"})
        if self.mode == "invalid_key":
            return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
        if self.mode == "rate_limit" or model in self.bad_models:
            return httpx.Response(429, json={"error": {"message": "Rate limit reached"}}, headers={"retry-after": "1"})
        if self.mode == "daily_quota":
            return httpx.Response(
                429,
                json={"error": {"message": f"Rate limit reached for model {model} on tokens per day (TPD)"}},
                headers={"retry-after": "3600"},
            )
        if self.mode == "server_error":
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        if self.mode == "broken_json" or (self.broken_once and len(self.calls) == 1):
            return self._completion("this is not json at all")
        if "You are evaluating two AI models" in prompt:
            ids = re.findall(r"^\[(e\d+)\]$", prompt, re.M)
            scores = [{"id": i, "a_correctness": 2, "a_style": 2, "b_correctness": 5, "b_style": 4} for i in ids]
            return self._completion(json.dumps({"scores": scores}))
        if "reviewing training data" in prompt:
            ids = re.findall(r"^\[(p\d+)\]$", prompt, re.M)
            scores = []
            for pid in ids:
                self._judged += 1
                low = self.low_score_every and self._judged % self.low_score_every == 0
                c, s = (2, 2) if low else self.judge_scores
                scores.append({"id": pid, "correctness": c, "style": s, "reason": "ok"})
            return self._completion(json.dumps({"scores": scores}))
        if "instruction-tuning data" in prompt:
            n = int(re.search(r"Write (\d+) new examples", prompt).group(1))  # type: ignore[union-attr]
            items = []
            for i in range(n):
                tag = uuid.uuid4().hex
                passage = f"Passage {tag[:10]} about the device." if i % 2 == 0 else ""
                items.append({"instruction": f"Summarize {tag[:12]}.", "input": passage, "output": f"Done {tag}."})
            return self._completion(json.dumps({"items": items}))
        if "multi-turn conversation data" in prompt:
            n = int(re.search(r"Write (\d+) new conversations", prompt).group(1))  # type: ignore[union-attr]
            convs = []
            for _ in range(n):
                tag = uuid.uuid4().hex
                convs.append(
                    {
                        "messages": [
                            {"role": "user", "content": f"What is {tag[:12]}?"},
                            {"role": "assistant", "content": f"It is {tag}."},
                            {"role": "user", "content": f"And how does {tag[12:20]} work?"},
                            {"role": "assistant", "content": f"Like this {tag[::-1]}."},
                        ]
                    }
                )
            # one malformed conversation (two user turns in a row) that must be skipped on its own
            convs.append({"messages": [{"role": "user", "content": "a?"}, {"role": "user", "content": "b?"}]})
            return self._completion(json.dumps({"conversations": convs}))
        n = int(re.search(r"Write (\d+) new question-answer pairs", prompt).group(1))  # type: ignore[union-attr]
        pairs = []
        for _ in range(n):
            tag = uuid.uuid4().hex
            pairs.append({"question": f"What about {tag[:12]} {tag[12:20]}?", "answer": f"Answer {tag} {tag[::-1]}."})
        return self._completion(json.dumps({"pairs": pairs}))

    @staticmethod
    def _completion(content: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "x",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        )

    def models(self, _request: httpx.Request) -> httpx.Response:
        if self.mode == "invalid_key":
            return httpx.Response(401, json={"error": {"message": "Invalid API Key"}})
        return httpx.Response(200, json={"object": "list", "data": [{"id": "openai/gpt-oss-120b", "object": "model"}]})


@contextmanager
def fake_groq() -> Iterator[FakeProvider]:
    """Route every provider HTTP call to the fake (and fail loudly on anything unexpected)."""
    fake = FakeProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == f"{GROQ}/chat/completions":
            return fake.reply(request)
        if url == f"{GROQ}/models":
            return fake.models(request)
        raise AssertionError(f"unexpected provider call: {request.method} {url}")

    previous = llm_client.test_transport
    llm_client.test_transport = httpx.MockTransport(handler)
    try:
        yield fake
    finally:
        llm_client.test_transport = previous
