"""Validate a custom Hugging Face base model (docs/plan/05 §2). Metadata only — never weights."""

import json
import re
from typing import Any, Literal

import httpx
import redis
from pydantic import BaseModel

from doctune.core.config import get_settings

HF_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,95}$")
HF_API = "https://huggingface.co/api/models"
PERMISSIVE = {"apache-2.0", "mit"}
# model_type values Unsloth fine-tunes (verify against Unsloth docs when upgrading)
UNSLOTH_SUPPORTED = {
    "llama",
    "mistral",
    "qwen2",
    "qwen3",
    "qwen3_5",
    "qwen3_moe",
    "gemma",
    "gemma2",
    "gemma3",
    "phi3",
    "phi4",
    "granite",
    "olmo2",
    "cohere",
}
QLORA_MAX_B = 10.0
LORA16_MAX_B = 4.5

# tests install a transport here so no request reaches huggingface.co
test_transport: httpx.BaseTransport | None = None


class ModelCheck(BaseModel):
    hf_id: str
    ok: bool
    architecture: str | None = None
    params_b: float | None = None
    license: str | None = None
    license_ok: bool = False
    gated: bool = False
    is_llama: bool = False
    train_mode: Literal["lora16", "qlora4"] = "qlora4"
    fits_t4: Literal["yes", "maybe", "no"] = "no"
    warnings: list[str] = []
    blocking: list[str] = []


def _client() -> httpx.Client:
    token = get_settings().hf_token_readonly
    headers = {"Authorization": f"Bearer {token.get_secret_value()}"} if token else {}
    return httpx.Client(timeout=15, headers=headers, transport=test_transport)


def _params_b(info: dict[str, Any]) -> float | None:
    total = (info.get("safetensors") or {}).get("total")
    if total:
        return round(float(total) / 1e9, 2)
    return None


def check(hf_id: str) -> ModelCheck:
    if not HF_ID_RE.match(hf_id):
        return ModelCheck(hf_id=hf_id, ok=False, blocking=["invalid_id"])
    cache = redis.Redis.from_url(get_settings().redis_url)
    cached = cache.get(f"hfcheck:{hf_id}")
    if cached:
        return ModelCheck.model_validate_json(cached)  # type: ignore[arg-type]
    result = _check_uncached(hf_id)
    cache.set(f"hfcheck:{hf_id}", result.model_dump_json(), ex=86_400)
    return result


def _check_uncached(hf_id: str) -> ModelCheck:
    out = ModelCheck(hf_id=hf_id, ok=False)
    with _client() as client:
        r = client.get(f"{HF_API}/{hf_id}", params={"expand[]": ["safetensors", "cardData", "config", "gated", "tags"]})
        if r.status_code in (401, 404):
            out.blocking.append("not_found")
            return out
        r.raise_for_status()
        info = r.json()
        config = info.get("config") or {}
        if not config.get("model_type"):
            cfg = client.get(f"https://huggingface.co/{hf_id}/resolve/main/config.json")
            if cfg.status_code == 200:
                config = json.loads(cfg.text)

    model_type = str(config.get("model_type") or "").lower() or None
    out.architecture = model_type
    out.gated = bool(info.get("gated"))
    card = info.get("cardData") or {}
    tags = info.get("tags") or []
    license_ = card.get("license") or next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None)
    out.license = str(license_).lower() if license_ else None
    out.license_ok = out.license in PERMISSIVE
    out.is_llama = bool(out.license and out.license.startswith("llama")) or (
        model_type == "llama" and hf_id.lower().startswith("meta-llama/")
    )
    out.params_b = _params_b(info)

    if model_type not in UNSLOTH_SUPPORTED:
        out.blocking.append("unsupported_architecture")
    out.train_mode = "lora16" if model_type and model_type.startswith("qwen3_5") else "qlora4"
    limit = LORA16_MAX_B if out.train_mode == "lora16" else QLORA_MAX_B
    if out.params_b is None:
        out.warnings.append("size_unknown")
        out.fits_t4 = "maybe"
    elif out.params_b > limit:
        out.blocking.append("too_large")
    else:
        out.fits_t4 = "maybe" if out.params_b > 7.5 else "yes"
        if out.params_b > 7.5:
            out.warnings.append("may_not_fit")
    if not out.license_ok:
        out.warnings.append("license_review")
    if out.gated:
        out.warnings.append("gated_requires_token")
    out.ok = not out.blocking
    return out
