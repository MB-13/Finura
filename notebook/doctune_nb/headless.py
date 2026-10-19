"""Headless run: the notebook's cell flow without prompts, for automatic training (Kaggle backend, ADR-0002).

    from doctune_nb.headless import run
    raise SystemExit(run(token=..., api_url=...))

or, for a local GPU machine:

    DOCTUNE_JOB_TOKEN=dtj_... DOCTUNE_API_URL=https://... python -m doctune_nb.headless

Flow (same calls as cells 2-4 and 7-9): DocTuneClient -> env.check -> config -> train -> evaluate -> upload adapter +
finish. No Google Drive, no Hugging Face token, no optional exports (GGUF / merged). Resuming needs nothing special:
`train.run` always fetches the latest checkpoint from DocTune and continues from it, so a relaunched kernel picks up
where the previous session stopped.

Only for runtimes DocTune starts through an official API in the user's own account (Kaggle). The Colab notebook stays
interactive (Colab free-tier rules) and must not use this module.

Exit codes (see EXIT_*): 0 done; 1 failed (reported to DocTune when possible); 2 usage (missing env vars, `-m` only);
3 cancelled / token rejected / job already ended; 4 no GPU (reported as pause no_gpu); 5 out of GPU memory before
the first step (reported as a fatal failure); 6 interrupted - SIGTERM / Ctrl-C (checkpoint saved, paused
session_ended). The job token is never printed.
"""

from __future__ import annotations

import os
import shutil
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import __version__, evaluate, export, train, ui
from doctune_nb import env as env_mod
from doctune_nb.api import DocTuneClient, NotebookOutdated, TokenError
from doctune_nb.callbacks import _Callback

if TYPE_CHECKING:
    from doctune_nb.api import JobConfig
    from doctune_nb.evaluate import EvalResult
    from doctune_nb.train import TrainResult

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 3
EXIT_NO_GPU = 4
EXIT_OOM = 5
EXIT_INTERRUPTED = 6

TOKEN_ENV = "DOCTUNE_JOB_TOKEN"
API_URL_ENV = "DOCTUNE_API_URL"
KAGGLE_WORKDIR = Path("/kaggle/working/doctune")  # measured: ~20 GB free (spike, ADR-0002)
PROGRESS_LOG_SECONDS = 60.0

HEADLESS_GATED_HINT = (
    "the model may be gated on Hugging Face; automatic training has no Hugging Face token - train this project "
    "with the Colab notebook and enter your token there"
)


class ProgressLog(_Callback):
    """One plain log line (step, %, loss) at most every `every_s` seconds - readable in a kernel log."""

    def __init__(
        self, max_steps: int, every_s: float = PROGRESS_LOG_SECONDS, clock: Callable[[], float] = time.monotonic
    ):
        self.max_steps, self.every_s, self.clock = max_steps, every_s, clock
        self.last: float | None = None

    def on_log(self, args: Any, state: Any, control: Any, logs: dict[str, Any] | None = None, **kwargs: Any) -> None:
        now = self.clock()
        total = int(getattr(state, "max_steps", 0) or self.max_steps or 1)
        step = int(state.global_step)
        if self.last is not None and now - self.last < self.every_s and step < total:
            return
        self.last = now
        loss = (logs or {}).get("loss")
        loss_txt = f", loss {float(loss):.4f}" if isinstance(loss, (int, float)) else ""
        ui.info(f"Step {step}/{total} ({ui.percent(step, total)}%){loss_txt}")


def _track_reports(client: DocTuneClient) -> list[str]:
    """Record pause()/fail() calls made by the package, so a failure is reported to DocTune exactly once."""
    calls: list[str] = []
    for name in ("pause", "fail"):
        original = getattr(client, name)

        def wrapped(*args: Any, _name: str = name, _orig: Callable[..., Any] = original, **kwargs: Any) -> Any:
            calls.append(_name)
            return _orig(*args, **kwargs)

        setattr(client, name, wrapped)
    return calls


@contextmanager
def _sigterm_as_interrupt() -> Iterator[None]:
    """SIGTERM (runtime shutting down) -> KeyboardInterrupt, so training saves a checkpoint and pauses first.
    A second SIGTERM is ignored while that happens. Only possible on the main thread."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    seen = [False]

    def handler(signum: int, frame: Any) -> None:
        if seen[0]:
            ui.warn("Shutdown signal received again; still saving progress.")
            return
        seen[0] = True
        ui.warn("The runtime is shutting down; saving progress.")
        raise KeyboardInterrupt

    try:
        previous = signal.signal(signal.SIGTERM, handler)
    except (ValueError, OSError):  # pragma: no cover - unusual runtimes
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _prepare_runtime(platform: str) -> None:
    os.environ.setdefault("TQDM_MININTERVAL", "60")  # library progress bars (Trainer, HF): one redraw a minute
    if platform == "kaggle" and "CUDA_VISIBLE_DEVICES" not in os.environ:
        # Kaggle gives 2 x T4; DocTune trains on one (as measured in the spike).
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"
        torch = sys.modules.get("torch")
        cuda = getattr(torch, "cuda", None)
        if cuda is not None and getattr(cuda, "is_initialized", lambda: False)():
            ui.warn("CUDA was initialised before DocTune could select one GPU; set CUDA_VISIBLE_DEVICES=0 earlier.")


def _resolve_workdir(workdir: str | os.PathLike[str] | None, platform: str) -> Path | None:
    if workdir is not None:
        return Path(workdir)
    if os.environ.get("DOCTUNE_WORKDIR"):
        return None  # env.workdir() honours it
    if platform == "kaggle":
        return KAGGLE_WORKDIR
    return None


def _evaluate(client: DocTuneClient, cfg: JobConfig, result: TrainResult) -> EvalResult | None:
    """Evaluation problems must not cost the trained model: on error, upload the adapter without scores."""
    try:
        return evaluate.run(client, cfg, result)
    except (TokenError, KeyboardInterrupt):
        raise
    except Exception as exc:
        ui.warn(
            f"Evaluation failed ({type(exc).__name__}: {str(exc)[:300]}). Uploading the adapter without evaluation "
            "scores."
        )
        train._free_gpu()
        return None


def _report_failure(client: DocTuneClient | None, reported: list[str], message: str) -> None:
    if client is None or reported:
        return
    try:
        client.fail(message, fatal=False)
    except Exception as exc:
        ui.warn(f"Could not report the failure to DocTune ({exc}).")


def run(
    token: str,
    api_url: str,
    *,
    workdir: str | os.PathLike[str] | None = None,
    cleanup: bool | None = None,
) -> int:
    """Train, evaluate and upload one DocTune job without any prompts. Returns a process exit code (EXIT_*).

    `workdir`: where data/checkpoints go (default: DOCTUNE_WORKDIR, else /kaggle/working/doctune on Kaggle, else
    ~/doctune). `cleanup`: delete this job's local files at the end (default: on Kaggle only, so the kernel's saved
    output stays small).
    """
    ui.set_headless(True)
    platform = env_mod.detect_platform()
    _prepare_runtime(platform)
    root = _resolve_workdir(workdir, platform)
    cleanup = platform == "kaggle" if cleanup is None else cleanup
    ui.info(f"DocTune headless run (doctune-nb {__version__}, platform {platform}).")

    client: DocTuneClient | None = None
    cfg: JobConfig | None = None
    reported: list[str] = []
    stage = "connecting"
    try:
        with _sigterm_as_interrupt():
            client = DocTuneClient(token, api_url)
            reported = _track_reports(client)
            stage = "GPU check"
            env = env_mod.check(client)
            stage = "loading the job"
            cfg = client.config()
            ui.show_config(cfg)
            stage = "training"
            result = train.run(
                client,
                cfg,
                env,
                hf_token=None,
                workdir=root,
                extra_callbacks=[ProgressLog(cfg.max_steps)],
                interrupt_reason="session_ended",
                gated_hint=HEADLESS_GATED_HINT,
            )
            stage = "evaluation"
            eval_result = _evaluate(client, cfg, result)
            stage = "uploading the adapter"
            export.upload_adapter_and_finish(client, cfg, result, eval_result, hf_token=None)
        ui.info("Headless run finished.")
        return EXIT_OK
    except TokenError as exc:
        ui.warn(
            f"DocTune no longer accepts this job token ({exc.code or 'token_error'}); the job was cancelled or "
            "has ended. Stopping."
        )
        return EXIT_CANCELLED
    except train.JobCancelled as exc:
        ui.warn(exc.message)
        return EXIT_CANCELLED
    except env_mod.NoGPU:
        return EXIT_NO_GPU  # already reported (pause no_gpu) and printed by env.check
    except train.TrainingOOM as exc:
        ui.error(exc.message)
        return EXIT_OOM  # already reported (fatal fail)
    except train.TrainingInterrupted as exc:
        ui.warn(exc.message)
        return EXIT_INTERRUPTED  # checkpoint saved, paused session_ended
    except KeyboardInterrupt:
        ui.warn(f"Interrupted during {stage}. Progress up to the last checkpoint is saved in DocTune.")
        return EXIT_INTERRUPTED
    except ui.StopNotebook as exc:
        ui.error(exc.message)
        _report_failure(client, reported, f"{stage}: {exc.message}")
        return EXIT_FAILED
    except NotebookOutdated as exc:
        ui.error(f"{exc} (installed doctune-nb {__version__}).")
        return EXIT_FAILED
    except Exception as exc:
        msg = f"{type(exc).__name__}: {str(exc)[:500]}"
        ui.error(f"Failed during {stage}: {msg}")
        traceback.print_exc(file=sys.stderr)
        _report_failure(client, reported, f"{stage}: {msg}")
        return EXIT_FAILED
    finally:
        if cleanup and cfg is not None:
            base = root or env_mod.workdir()
            shutil.rmtree(base / "jobs" / cfg.job_id, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """`python -m doctune_nb.headless`: token and API URL come from DOCTUNE_JOB_TOKEN / DOCTUNE_API_URL."""
    del argv  # no options; everything comes from the environment
    token = os.environ.get(TOKEN_ENV, "").strip()
    api_url = os.environ.get(API_URL_ENV, "").strip()
    missing = [name for name, value in ((TOKEN_ENV, token), (API_URL_ENV, api_url)) if not value]
    if missing:
        ui.error(f"Set {' and '.join(missing)} to run DocTune training headlessly.")
        return EXIT_USAGE
    return run(token=token, api_url=api_url)


if __name__ == "__main__":
    raise SystemExit(main())
