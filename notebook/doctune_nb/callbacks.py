"""Trainer callbacks: heartbeats, time-based checkpoints, checkpoint upload.

These classes duck-type `transformers.TrainerCallback` (the Trainer calls `getattr(cb, event)(args, state, control,
**kwargs)` for every event) so this module imports without transformers - and so it never imports transformers
before Unsloth has patched it. No background threads: everything runs synchronously inside trainer events.
"""

from __future__ import annotations

import json
import math
import os
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import ui
from doctune_nb.api import DocTuneError, TokenError

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient

META_FILE = "doctune_meta.json"


class _Callback:
    """No-op implementations of every TrainerCallback event (unknown future events resolve to no-ops too)."""

    def __getattr__(self, name: str) -> Callable[..., None]:
        if name.startswith("on_"):
            return lambda *args, **kwargs: None
        raise AttributeError(name)

    def on_init_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_train_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_epoch_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_epoch_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_step_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_pre_optimizer_step(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_optimizer_step(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_substep_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_evaluate(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_predict(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_log(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_prediction_step(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...
    def on_push_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None: ...


def _finite(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class HeartbeatCallback(_Callback):
    """Sends step / max_steps / loss / lr / epoch at most every `every_s` seconds; stops on cancel."""

    def __init__(
        self,
        client: DocTuneClient,
        max_steps: int,
        *,
        every_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.client, self.max_steps, self.every_s, self.clock = client, max_steps, every_s, clock
        self.last_sent: float | None = None
        self.loss: float | None = None
        self.lr: float | None = None
        self.epoch: float | None = None
        self.cancelled = False
        self.sent = 0
        self.nan_steps = 0

    def _max(self, state: Any) -> int:
        return int(getattr(state, "max_steps", 0) or self.max_steps or 1)

    def send(self, state: Any, control: Any, *, force: bool = False) -> None:
        now = self.clock()
        if not force and self.last_sent is not None and now - self.last_sent < self.every_s:
            return
        self.last_sent = now
        try:
            out = self.client.heartbeat(state.global_step, self._max(state), self.loss, self.lr, self.epoch)
            self.sent += 1
        except TokenError as exc:
            # token revoked / job cancelled from the dashboard
            self._cancel(control, f"DocTune rejected the job token ({exc}). Stopping training.")
            return
        except Exception as exc:  # network trouble must never crash training
            ui.warn(f"Heartbeat failed ({exc}); training continues.")
            return
        if out.get("cancel_requested"):
            self._cancel(control, "Training was cancelled from the DocTune dashboard. Stopping.")

    def _cancel(self, control: Any, msg: str) -> None:
        if not self.cancelled:
            ui.warn(msg)
        self.cancelled = True
        control.should_training_stop = True

    def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.send(state, control, force=True)

    def on_log(self, args: Any, state: Any, control: Any, logs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        logs = logs or {}
        if "loss" in logs:
            loss = _finite(logs["loss"])
            if loss is None:
                self.nan_steps += 1
                ui.warn(f"Loss is not a number at step {state.global_step} (fp16 overflow?).")
            self.loss = loss
        if "learning_rate" in logs:
            self.lr = _finite(logs["learning_rate"])
        if "epoch" in logs:
            self.epoch = _finite(logs["epoch"])
        self.send(state, control)

    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.send(state, control)

    def on_train_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.send(state, control, force=True)


class TimedCheckpointCallback(_Callback):
    """Forces a save when `every_minutes` have passed since the last one (guards against slow steps)."""

    def __init__(self, every_minutes: float, *, clock: Callable[[], float] = time.monotonic):
        self.every_s = max(60.0, float(every_minutes) * 60.0)
        self.clock = clock
        self.last_save: float | None = None
        self.last_saved_step = -1

    def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.last_save = self.clock()
        self.last_saved_step = state.global_step

    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        if self.last_save is None:
            self.last_save = self.clock()
        if self.clock() - self.last_save >= self.every_s and state.global_step > self.last_saved_step:
            control.should_save = True

    def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.last_save = self.clock()
        self.last_saved_step = state.global_step


def zip_checkpoint(ckpt_dir: str | os.PathLike[str], zip_path: str | os.PathLike[str], meta: dict[str, Any]) -> Path:
    """ZIP_STORED (tensors don't compress) with files at the archive root plus doctune_meta.json."""
    ckpt_dir, zip_path = Path(ckpt_dir), Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for p in sorted(ckpt_dir.rglob("*")):
            if p.is_file() and p.name != META_FILE:
                z.write(p, p.relative_to(ckpt_dir).as_posix())
        z.writestr(META_FILE, json.dumps(meta, indent=2))
    return zip_path


def unzip_checkpoint(zip_path: str | os.PathLike[str], dest_dir: str | os.PathLike[str]) -> tuple[Path, dict]:
    """Extract safely (no absolute paths / ..) and return (dir, meta)."""
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = (dest / name).resolve()
            if not target.is_relative_to(dest):
                raise DocTuneError(f"Checkpoint archive contains an unsafe path: {name}")
        z.extractall(dest)
    meta_path = dest / META_FILE
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return dest, meta


class UploadCheckpointCallback(_Callback):
    """on_save -> zip the new checkpoint -> pre-signed PUT -> complete. Failures are retried, never fatal."""

    def __init__(
        self,
        client: DocTuneClient,
        meta: dict[str, Any],
        zip_dir: str | os.PathLike[str],
        *,
        attempts: int = 3,
        retry_wait_s: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client, self.meta, self.zip_dir = client, meta, Path(zip_dir)
        self.attempts, self.retry_wait_s, self.sleep = attempts, retry_wait_s, sleep
        self.uploaded_steps: list[int] = []
        self.failed_steps: list[int] = []

    def upload_dir(self, ckpt_dir: str | os.PathLike[str], step: int, control: Any | None = None) -> bool:
        if step in self.uploaded_steps:
            return True
        if not Path(ckpt_dir).is_dir():
            ui.warn(f"Checkpoint folder {ckpt_dir} not found; nothing uploaded.")
            self.failed_steps.append(step)
            return False
        zip_path = self.zip_dir / "checkpoint.zip"
        t0 = time.monotonic()
        try:
            zip_checkpoint(ckpt_dir, zip_path, {**self.meta, "step": step})
            for attempt in range(1, self.attempts + 1):
                try:
                    self.client.upload_checkpoint(zip_path, step)
                    self.uploaded_steps.append(step)
                    size = os.path.getsize(zip_path)
                    ui.info(
                        f"Checkpoint saved at step {step} ({ui.human_bytes(size)}, "
                        f"{time.monotonic() - t0:.0f} s). Progress is safe if the session ends."
                    )
                    return True
                except TokenError as exc:
                    ui.warn(f"Checkpoint upload refused: {exc}")
                    if control is not None:
                        control.should_training_stop = True
                    break
                except Exception as exc:
                    if attempt < self.attempts:
                        ui.warn(f"Checkpoint upload failed ({exc}); retrying ({attempt}/{self.attempts}).")
                        self.sleep(self.retry_wait_s * attempt)
                    else:
                        ui.warn(
                            f"Checkpoint upload failed ({exc}). Training continues; the next checkpoint will try again."
                        )
        except Exception as exc:  # zip errors (disk full, ...) must not crash training
            ui.warn(f"Could not package the checkpoint ({exc}). Training continues.")
        finally:
            if zip_path.exists():
                zip_path.unlink()
        self.failed_steps.append(step)
        return False

    def on_save(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        ckpt = Path(args.output_dir) / f"checkpoint-{state.global_step}"
        self.upload_dir(ckpt, state.global_step, control)
