from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from doctune.training import hf_check


def model_info(
    model_type: str, license_: str | None = "apache-2.0", params: float | None = 4e9, gated: bool = False
) -> dict[str, Any]:
    info: dict[str, Any] = {"config": {"model_type": model_type}, "gated": gated, "tags": []}
    if license_:
        info["cardData"] = {"license": license_}
    if params:
        info["safetensors"] = {"total": params}
    return info


@pytest.fixture
def hf(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Fake huggingface.co: tests put model infos in the returned dict."""
    models: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        repo = request.url.path.removeprefix("/api/models/")
        if repo in models:
            return httpx.Response(200, json=models[repo])
        return httpx.Response(404)

    monkeypatch.setattr(hf_check, "test_transport", httpx.MockTransport(handler))
    import redis

    r = redis.Redis.from_url("redis://localhost:56379/0")
    for key in r.scan_iter("hfcheck:*"):
        r.delete(key)
    yield models


def test_permissive_model_passes(hf: dict[str, Any]) -> None:
    hf["acme/qwen-ft"] = model_info("qwen3")
    c = hf_check.check("acme/qwen-ft")
    assert c.ok and c.license_ok and c.train_mode == "qlora4" and c.fits_t4 == "yes"
    assert c.warnings == []


def test_qwen35_uses_lora16_and_smaller_limit(hf: dict[str, Any]) -> None:
    hf["acme/q35-9b"] = model_info("qwen3_5", params=9e9)
    c = hf_check.check("acme/q35-9b")
    assert c.train_mode == "lora16" and "too_large" in c.blocking and not c.ok


def test_unsupported_architecture_blocked(hf: dict[str, Any]) -> None:
    hf["acme/weird"] = model_info("mamba_custom")
    assert "unsupported_architecture" in hf_check.check("acme/weird").blocking


def test_license_and_gated_warnings(hf: dict[str, Any]) -> None:
    hf["meta-llama/Llama-3.1-8B-Instruct"] = model_info("llama", "llama3.1", 8e9, gated=True)
    c = hf_check.check("meta-llama/Llama-3.1-8B-Instruct")
    assert c.ok and c.is_llama and not c.license_ok
    assert {"license_review", "gated_requires_token", "may_not_fit"} <= set(c.warnings)


def test_too_large_and_not_found(hf: dict[str, Any]) -> None:
    hf["acme/huge"] = model_info("llama", params=70e9)
    assert "too_large" in hf_check.check("acme/huge").blocking
    assert hf_check.check("acme/missing").blocking == ["not_found"]


@pytest.mark.parametrize("bad", ["", "no-slash", "../etc/passwd", "a/b/c", "http://evil.com/x", "a/" + "b" * 200])
def test_invalid_ids_never_reach_the_network(hf: dict[str, Any], bad: str) -> None:
    assert hf_check.check(bad).blocking == ["invalid_id"]
