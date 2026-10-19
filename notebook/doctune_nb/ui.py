"""User-facing messages for the notebook. Plain text, no emojis, never prints secrets."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")

PREFIX = "[DocTune]"

# Headless runs (Kaggle kernel, local script): plain log lines only, no progress-bar redraws in the log.
_HEADLESS = False


def set_headless(flag: bool = True) -> None:
    global _HEADLESS
    _HEADLESS = bool(flag)


def is_headless() -> bool:
    return _HEADLESS


# Same wording as the design doc's pause table and the server (routers/notebook.py PAUSE_MESSAGES).
PAUSE_MESSAGES = {
    "session_ended": "Your Colab session ended at {pct}%. Progress is saved. Open the notebook and run it again to "
    "continue.",
    "idle_timeout": "Colab disconnected because the tab was idle. Progress is saved at {pct}%. Run the notebook again "
    "and keep the tab open.",
    "no_gpu": "Colab has no free GPU for your account right now. Progress is saved at {pct}%. Try again later.",
    "stopped": "Training stopped at {pct}%. Progress is saved. Run the notebook again to continue.",
    "user_stopped": "You stopped training at {pct}%. Progress is saved. Run the notebook again to continue.",
}

NO_GPU_HELP = (
    "No GPU found. In Colab: Runtime -> Change runtime type -> T4 GPU -> Save, then run the notebook again. "
    "If a T4 is already selected, Colab has no free GPU for your account right now - try again later."
)

QWEN35_COMPILE_NOTE = (
    "Compiling kernels - the first training step takes about 5-6 minutes in each new Colab session. "
    "This is normal; keep the tab open."
)


def percent(step: int, max_steps: int) -> int:
    return int(100 * step / max_steps) if max_steps else 0


def pause_message(reason: str, step: int, max_steps: int) -> str:
    template = PAUSE_MESSAGES.get(reason, PAUSE_MESSAGES["stopped"])
    return template.format(pct=percent(step, max_steps))


def _out(level: str, msg: str) -> None:
    stream = sys.stderr if level in ("WARNING", "ERROR") else sys.stdout
    tag = f"{PREFIX} " if level == "INFO" else f"{PREFIX} {level}: "
    print(f"{tag}{msg}", file=stream, flush=True)


def info(msg: str) -> None:
    _out("INFO", msg)


def warn(msg: str) -> None:
    _out("WARNING", msg)


def error(msg: str) -> None:
    _out("ERROR", msg)


def step(title: str) -> None:
    print(f"\n{PREFIX} == {title} ==", flush=True)


def mask(secret: str | None) -> str:
    if not secret:
        return "<none>"
    return secret[:4] + "..." if len(secret) > 8 else "***"


def progress(iterable: Iterable[T], *, total: int | None = None, desc: str = "") -> Iterator[T]:
    """tqdm.auto progress bar when available (renders as a widget in Colab), plain iteration otherwise
    (and always in headless mode, where a redrawing bar would only clutter the log)."""
    if _HEADLESS:
        yield from iterable
        return
    try:
        from tqdm.auto import tqdm
    except ImportError:  # pragma: no cover - tqdm ships with the train extra
        yield from iterable
        return
    yield from tqdm(iterable, total=total, desc=desc)


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"  # pragma: no cover


def show_config(cfg: Any, checkpoint: dict[str, Any] | None = None) -> None:
    hp = cfg.hyperparams
    info(f"Project: {cfg.project_name}")
    info(f"Base model: {cfg.base_model_id} ({cfg.train_mode}, license: {cfg.base_model_license or 'unknown'})")
    info(
        f"Dataset: {cfg.dataset.train_count} training pairs, {cfg.dataset.eval_count} held out. "
        f"Epochs {hp.epochs}, LoRA r={hp.lora_r}, lr {hp.learning_rate:g}, batch {hp.batch_size}x{hp.grad_accum}, "
        f"max length {hp.max_seq_len}."
    )
    info(f"Training steps: {cfg.max_steps}. A checkpoint is saved about every {cfg.checkpoint_every_minutes} minutes.")
    if checkpoint and checkpoint.get("exists"):
        s = int(checkpoint.get("step") or 0)
        info(f"Resuming from step {s} ({percent(s, cfg.max_steps)}%).")


class StopNotebook(Exception):
    """Stops "Run all" with a short message instead of a long traceback (IPython honours _render_traceback_)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def _render_traceback_(self) -> list[str]:
        return [f"{PREFIX} {self.message}"]
