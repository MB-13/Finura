"""Training presets: hide hyperparameters from non-ML users (docs/plan/05 §3)."""

import math
from typing import Any, Literal

from pydantic import BaseModel, Field

PresetKey = Literal["quick", "balanced", "thorough"]


class Hyperparams(BaseModel):
    epochs: int = Field(ge=1, le=5)
    lora_r: Literal[8, 16, 32, 64]
    lora_alpha: int = Field(ge=8, le=128)
    learning_rate: float = Field(ge=1e-5, le=5e-4)
    batch_size: int = Field(ge=1, le=8)
    grad_accum: int = Field(ge=1, le=32)
    max_seq_len: int = Field(ge=512, le=4096)
    warmup_ratio: float = 0.05
    weight_decay: float = 0.01
    lr_scheduler: str = "cosine"
    optim: str = "adamw_8bit"
    checkpoint_minutes: int = 7


class Advanced(BaseModel):
    epochs: int | None = Field(default=None, ge=1, le=5)
    lora_r: Literal[8, 16, 32, 64] | None = None
    learning_rate: float | None = Field(default=None, ge=1e-5, le=5e-4)
    max_seq_len: int | None = Field(default=None, ge=512, le=4096)


class Preset(BaseModel):
    key: PresetKey
    name: str
    description: str
    hyperparams: Hyperparams


PRESETS: dict[str, Preset] = {
    "quick": Preset(
        key="quick",
        name="Quick",
        description="One pass over your data. Fastest; good for a first try.",
        hyperparams=Hyperparams(
            epochs=1, lora_r=16, lora_alpha=16, learning_rate=2e-4, batch_size=2, grad_accum=4, max_seq_len=1024
        ),
    ),
    "balanced": Preset(
        key="balanced",
        name="Balanced",
        description="Two passes. The best default for most datasets.",
        hyperparams=Hyperparams(
            epochs=2, lora_r=16, lora_alpha=32, learning_rate=2e-4, batch_size=2, grad_accum=4, max_seq_len=2048
        ),
    ),
    "thorough": Preset(
        key="thorough",
        name="Thorough",
        description="Three passes with a larger adapter. Slower.",
        hyperparams=Hyperparams(
            epochs=3, lora_r=32, lora_alpha=64, learning_rate=1e-4, batch_size=2, grad_accum=4, max_seq_len=2048
        ),
    ),
}


def resolve(preset: str, advanced: Advanced | None, params_b: float) -> Hyperparams:
    hp = PRESETS[preset].hyperparams.model_copy()
    if advanced:
        updates: dict[str, Any] = advanced.model_dump(exclude_none=True)
        if "lora_r" in updates:
            updates["lora_alpha"] = updates["lora_r"] * (hp.lora_alpha // hp.lora_r)
        hp = hp.model_copy(update=updates)
    if params_b >= 7.5:  # large models: smaller batches and sequences to fit a T4
        hp = hp.model_copy(update={"batch_size": 1, "grad_accum": 8, "max_seq_len": min(hp.max_seq_len, 1024)})
    return Hyperparams.model_validate(hp.model_dump())


def max_steps(train_pairs: int, hp: Hyperparams) -> int:
    return max(1, math.ceil(train_pairs * hp.epochs / (hp.batch_size * hp.grad_accum)))


def estimate_minutes(steps: int, sec_per_step: float, startup_min: float, avg_tokens: float) -> float:
    """sec_per_step was measured with ~88-token examples; scale roughly linearly with length."""
    scale = max(1.0, avg_tokens / 88)
    return round(startup_min + steps * sec_per_step * scale / 60, 1)
