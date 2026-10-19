"""Generation providers and their free-tier limits.

Verified 2026-10-07 (docs/runbooks/free-tiers.md). Limits are per *model* (Groq) or per project
(Gemini, shown only in AI Studio), so the unit of rotation is a (provider, model) pair. Real limits
are also learned at runtime from rate-limit headers.
"""

from dataclasses import dataclass, field

from doctune.models.generation import Provider


@dataclass(frozen=True)
class ModelSpec:
    id: str
    rpm: int
    tpm: int
    rpd: int | None = None
    tpd: int | None = None
    license: str | None = None
    json_mode: bool = True


@dataclass(frozen=True)
class ProviderSpec:
    provider: Provider
    name: str
    base_url: str
    models: tuple[ModelSpec, ...]
    requires_terms_ack: bool = False
    note: str | None = None
    key_help_url: str = ""
    extra: dict[str, str] = field(default_factory=dict)


PROVIDERS: dict[Provider, ProviderSpec] = {
    Provider.groq: ProviderSpec(
        provider=Provider.groq,
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        models=(
            ModelSpec("openai/gpt-oss-120b", rpm=30, tpm=8_000, rpd=1_000, tpd=200_000, license="apache-2.0"),
            ModelSpec("qwen/qwen3.8-27b", rpm=30, tpm=8_000, rpd=1_000, tpd=200_000, license="apache-2.0"),
            ModelSpec("openai/gpt-oss-20b", rpm=30, tpm=8_000, rpd=1_000, tpd=200_000, license="apache-2.0"),
        ),
        key_help_url="https://console.groq.com/keys",
    ),
    Provider.gemini: ProviderSpec(
        provider=Provider.gemini,
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        models=(ModelSpec("gemini-flash-latest", rpm=10, tpm=250_000, rpd=250),),
        requires_terms_ack=True,
        note="Google's terms restrict using outputs to build competing models. Not available in the EU/UK.",
        key_help_url="https://aistudio.google.com/apikey",
    ),
    Provider.cerebras: ProviderSpec(
        provider=Provider.cerebras,
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        models=(
            ModelSpec("gpt-oss-120b", rpm=5, tpm=30_000, tpd=1_000_000, license="apache-2.0"),
            ModelSpec("qwen-3.8-27b", rpm=5, tpm=30_000, tpd=1_000_000, license="apache-2.0"),
        ),
        note="Needs a payment method; free credits expire after 30 days.",
        key_help_url="https://cloud.cerebras.ai",
    ),
}


def model_spec(provider: Provider, model_id: str) -> ModelSpec:
    for m in PROVIDERS[provider].models:
        if m.id == model_id:
            return m
    # unknown model chosen by the user: assume conservative limits
    return ModelSpec(model_id, rpm=10, tpm=8_000)
