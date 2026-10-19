from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_api import TOKEN, FakeApi, FakeState  # noqa: E402

from doctune_nb.api import DocTuneClient  # noqa: E402


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-slow", action="store_true", default=False, help="run the CPU smoke test (downloads)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow"):
        return
    skip = pytest.mark.skip(reason="slow: needs --run-slow (downloads a tiny model, needs the [smoke] extra)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def api():
    with FakeApi(FakeState()) as fake:
        yield fake


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(api: FakeApi, sleeps: list[float]) -> DocTuneClient:
    return DocTuneClient(TOKEN, api.url, sleep=sleeps.append, backoff_s=0.01, retries=3)


class ChatmlTokenizer:
    """Minimal stand-in for a Qwen3 tokenizer's chat template (non-thinking adds an empty think block)."""

    eos_token = "<|im_end|>"
    pad_token = None

    def __init__(self, thinking_kw: bool = True):
        self.thinking_kw = thinking_kw
        self.calls: list[dict[str, Any]] = []

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False, **kw):
        if "enable_thinking" in kw and not self.thinking_kw:
            raise TypeError("unexpected keyword enable_thinking")
        self.calls.append(kw)
        think = "<think>\n\n</think>\n\n" if kw.get("enable_thinking") is False else ""
        out = ""
        for i, m in enumerate(messages):
            last = i == len(messages) - 1
            body = (think + m["content"]) if (m["role"] == "assistant" and last) else m["content"]
            out += f"<|im_start|>{m['role']}\n{body}<|im_end|>\n"
        if add_generation_prompt:
            out += "<|im_start|>assistant\n" + think
        return out


@pytest.fixture
def chatml_tok() -> ChatmlTokenizer:
    return ChatmlTokenizer()
