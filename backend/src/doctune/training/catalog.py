"""Curated base models (ADR-0001). One place for the UI cards, validation and the playground."""

from dataclasses import dataclass
from typing import Literal

TrainMode = Literal["lora16", "qlora4"]
FitsT4 = Literal["yes", "unconfirmed"]

# Versions measured in the Colab spike (ADR-0001); the notebook pins exactly these.
LIB_VERSIONS: dict[str, str] = {
    "unsloth": "2026.10.1",
    "unsloth_zoo": "2026.10.1",
    "torch": "2.11.0",
    "transformers": "5.17.0",
    "trl": "1.13.0",
    "peft": "0.21.1",
    "bitsandbytes": "0.50.2",
}


@dataclass(frozen=True)
class BaseModel:
    id: str  # Hugging Face repo
    display_name: str
    params_b: float
    license: str
    train_mode: TrainMode
    fits_t4: FitsT4
    vram_gb: float  # measured or Unsloth-reported peak on a T4
    sec_per_step: float  # measured on a T4 with batch 2 x 4 and short examples; scaled by tokens later
    startup_min: float  # kernel compile + load per session
    recommended: bool = False
    playground_gguf: tuple[str, str] | None = None  # (HF repo, file) of the base GGUF for llama.cpp
    note: str | None = None


CATALOG: tuple[BaseModel, ...] = (
    BaseModel(
        "unsloth/Qwen3.5-4B",
        "Qwen3.5 4B",
        4,
        "apache-2.0",
        "lora16",
        "yes",
        9.7,
        3.0,
        8.0,
        True,
        ("unsloth/Qwen3.5-4B-GGUF", "Qwen3.5-4B-Q4_K_M.gguf"),
        "Best quality. The first minutes of each Colab session compile kernels.",
    ),
    BaseModel(
        "unsloth/Qwen3-4B",
        "Qwen3 4B (faster)",
        4,
        "apache-2.0",
        "qlora4",
        "yes",
        4.2,
        2.1,
        1.5,
        False,
        ("unsloth/Qwen3-4B-GGUF", "Qwen3-4B-Q4_K_M.gguf"),
        "About 1.4x faster, slightly weaker on facts.",
    ),
    BaseModel(
        "unsloth/Qwen3.5-2B",
        "Qwen3.5 2B",
        2,
        "apache-2.0",
        "lora16",
        "yes",
        5.0,
        1.8,
        6.0,
        False,
        ("unsloth/Qwen3.5-2B-GGUF", "Qwen3.5-2B-Q4_K_M.gguf"),
    ),
    BaseModel(
        "unsloth/Qwen3.5-0.8B",
        "Qwen3.5 0.8B",
        0.8,
        "apache-2.0",
        "lora16",
        "yes",
        3.0,
        1.0,
        5.0,
        False,
        ("unsloth/Qwen3.5-0.8B-GGUF", "Qwen3.5-0.8B-Q4_K_M.gguf"),
    ),
    BaseModel(
        "unsloth/Qwen3-1.7B",
        "Qwen3 1.7B",
        1.7,
        "apache-2.0",
        "qlora4",
        "yes",
        3.0,
        1.2,
        1.0,
        False,
        ("unsloth/Qwen3-1.7B-GGUF", "Qwen3-1.7B-Q4_K_M.gguf"),
    ),
    BaseModel(
        "unsloth/Qwen3-0.6B",
        "Qwen3 0.6B",
        0.6,
        "apache-2.0",
        "qlora4",
        "yes",
        2.0,
        0.8,
        1.0,
        False,
        ("unsloth/Qwen3-0.6B-GGUF", "Qwen3-0.6B-Q4_K_M.gguf"),
    ),
    BaseModel(
        "unsloth/Qwen3-8B",
        "Qwen3 8B (large)",
        8,
        "apache-2.0",
        "qlora4",
        "yes",
        8.3,
        5.0,
        2.0,
        False,
        ("unsloth/Qwen3-8B-GGUF", "Qwen3-8B-Q4_K_M.gguf"),
        "Slower to train. Chat with it on your own computer with Ollama.",
    ),
)
BY_ID = {m.id: m for m in CATALOG}
DEFAULT_MODEL = next(m for m in CATALOG if m.recommended)
