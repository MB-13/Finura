"""Headless run (Kaggle backend, ADR-0002): the cell flow without prompts, exit codes, resume, failure reporting.

The model, trainer and generator are fakes (no torch, no GPU); the DocTune API is the in-process FakeApi.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ChatmlTokenizer
from fake_api import TOKEN, FakeApi, FakeState
from test_train_flow import FakeTrainer, OutOfMemoryError

from doctune_nb import env as env_mod
from doctune_nb import evaluate, export, headless, train, ui
from doctune_nb.env import Env

T4 = Env(True, "Tesla T4", 15.6, False, "local", "3.13", "2.11.0", "12.8")


class SavingTokenizer(ChatmlTokenizer):
    def save_pretrained(self, path: str) -> None:
        Path(path, "tokenizer_config.json").write_text("{}")


class FakePeftModel:
    def save_pretrained(self, path: str) -> None:
        Path(path, "adapter_model.safetensors").write_bytes(b"W" * 1024)
        Path(path, "adapter_config.json").write_text('{"base_model_name_or_path": "x"}')


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Headless mode, env vars and the SIGTERM handler must not leak into other tests."""
    monkeypatch.setattr(ui, "_HEADLESS", False)
    for name in (
        "TQDM_MININTERVAL",
        "CUDA_VISIBLE_DEVICES",
        "KAGGLE_KERNEL_RUN_TYPE",
        "COLAB_RELEASE_TAG",
        "COLAB_GPU",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DOCTUNE_WORKDIR", str(tmp_path / "work"))
    monkeypatch.setattr(export, "hf_license_fetcher", lambda repo, token: None)  # no network
    previous = signal.getsignal(signal.SIGTERM)
    yield
    assert signal.getsignal(signal.SIGTERM) == previous  # handler restored


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace GPU detection, model loading, trainer and generator; returns knobs + a log of the flow's calls."""
    ctx: dict[str, Any] = {"env": T4, "behaviour": {}, "trainers": [], "load_exc": None, "gen_exc": None, "flow": []}

    real_check, real_config = env_mod.check, headless.DocTuneClient.config
    real_eval, real_upload = evaluate.run, export.upload_adapter_and_finish
    real_train = train.run

    def check(client: Any = None, **kw: Any) -> Env:
        ctx["flow"].append("env.check")
        return real_check(client, detect_fn=lambda: ctx["env"], **kw)

    def config(self: Any) -> Any:
        ctx["flow"].append("config")
        return real_config(self)

    def train_run(*a: Any, **kw: Any) -> Any:
        ctx["flow"].append("train")
        ctx["train_kwargs"] = kw
        return real_train(*a, **kw)

    def eval_run(*a: Any, **kw: Any) -> Any:
        ctx["flow"].append("evaluate")
        return real_eval(*a, **kw)

    def upload(*a: Any, **kw: Any) -> Any:
        ctx["flow"].append("upload")
        ctx["upload_kwargs"] = kw
        return real_upload(*a, **kw)

    def load_model(cfg: Any, **kw: Any) -> Any:
        if ctx["load_exc"]:
            raise ctx["load_exc"]
        return "model", SavingTokenizer()

    def build_trainer(model: Any, tok: Any, ds: Any, cfg: Any, out_dir: Path, callbacks: list[Any], **kw: Any) -> Any:
        t = FakeTrainer(out_dir, callbacks, cfg.max_steps, ctx["behaviour"], kw["batch_size"])
        t.model = FakePeftModel()
        ctx["trainers"].append(t)
        return t

    def hf_generator(model: Any, tok: Any, **kw: Any) -> Any:
        def gen(prompts: list[str], adapter: bool) -> list[str]:
            if ctx["gen_exc"]:
                raise ctx["gen_exc"]
            return [("Reference answer" if adapter else "no idea") for _ in prompts]

        return gen

    monkeypatch.setattr(env_mod, "check", check)
    monkeypatch.setattr(headless.DocTuneClient, "config", config)
    monkeypatch.setattr(train, "run", train_run)
    monkeypatch.setattr(evaluate, "run", eval_run)
    monkeypatch.setattr(export, "upload_adapter_and_finish", upload)
    monkeypatch.setattr(train, "load_model", load_model)
    monkeypatch.setattr(train, "build_trainer", build_trainer)
    monkeypatch.setattr(train, "to_hf_dataset", lambda texts: texts)
    monkeypatch.setattr(evaluate, "hf_generator", hf_generator)
    return ctx


def api_calls(api: FakeApi) -> list[str]:
    return [
        f"{r.method} {r.path.removeprefix('/jobs/current')}" for r in api.state.requests if r.path.startswith("/jobs")
    ]


def no_secret(capsys: pytest.CaptureFixture[str]) -> str:
    out = capsys.readouterr()
    text = out.out + out.err
    assert TOKEN not in text and TOKEN[4:20] not in text
    return text


# ------------------------------------------------------------------------------------------------ happy path


def test_happy_path_runs_cells_in_order(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_OK
    assert fakes["flow"] == ["env.check", "config", "train", "evaluate", "upload"]
    calls = api_calls(api)
    assert calls[0] == "GET /config"
    order = [c for c in calls if c in ("POST /start", "POST /training-complete", "POST /finish")]
    assert order == ["POST /start", "POST /training-complete", "POST /finish"]
    assert calls[-1] == "POST /finish"
    assert {"eval_generations", "adapter_safetensors"} <= set(api.state.artifacts)
    assert api.state.job_state == "completed" and not api.state.calls("POST", "/jobs/current/fail")
    # no Hugging Face token anywhere, interrupt -> session_ended, no optional exports
    assert fakes["train_kwargs"]["hf_token"] is None and fakes["upload_kwargs"]["hf_token"] is None
    assert fakes["train_kwargs"]["interrupt_reason"] == "session_ended"
    finish = api.state.calls("POST", "/jobs/current/finish")[0].json()
    assert finish["exports"] == {} and finish["metrics"]["rouge_l_tuned"] is not None
    text = no_secret(capsys)
    assert "Headless run finished" in text and "Traceback" not in text
    assert os.environ["TQDM_MININTERVAL"] == "60" and ui.is_headless()


def test_progress_is_plain_lines_in_headless_mode() -> None:
    ui.set_headless(True)
    assert list(ui.progress(iter([1, 2, 3]), total=3, desc="x")) == [1, 2, 3]
    from types import SimpleNamespace

    clock = iter([0.0, 10.0, 70.0, 75.0])
    cb = headless.ProgressLog(10, every_s=60, clock=lambda: next(clock))
    lines: list[str] = []
    orig = ui.info
    try:
        ui.info = lines.append  # type: ignore[assignment]
        for step in (1, 2, 3, 10):
            cb.on_log(None, SimpleNamespace(global_step=step, max_steps=10), None, logs={"loss": 0.5})
    finally:
        ui.info = orig  # type: ignore[assignment]
    assert lines == ["Step 1/10 (10%), loss 0.5000", "Step 3/10 (30%), loss 0.5000", "Step 10/10 (100%), loss 0.5000"]


# ------------------------------------------------------------------------------------------------ resume


def test_interrupt_then_relaunch_resumes_from_checkpoint(
    api: FakeApi, fakes: dict[str, Any], tmp_path: Path, monkeypatch, capsys
) -> None:
    fakes["behaviour"][4] = KeyboardInterrupt()
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_INTERRUPTED
    assert api.state.checkpoint["step"] == 4
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "session_ended", "step": 4}
    assert not api.state.calls("POST", "/jobs/current/fail")

    # the backend relaunches a fresh kernel (new disk): no prompt, resumes from the uploaded step-4 checkpoint
    fakes["behaviour"].clear()
    monkeypatch.setenv("DOCTUNE_WORKDIR", str(tmp_path / "session2"))
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_OK
    t = fakes["trainers"][-1]
    assert t.resumed_from.endswith("checkpoint-4") and t.state.global_step == 10
    assert api.state.calls("POST", "/jobs/current/start")[-1].json()["resumed_from_step"] == 4
    assert api.state.job_state == "completed"
    no_secret(capsys)


def test_sigterm_saves_checkpoint_and_pauses(api: FakeApi, fakes: dict[str, Any], monkeypatch, capsys) -> None:
    class SigtermAt(headless.ProgressLog):
        def on_log(self, args: Any, state: Any, control: Any, logs: Any = None, **kw: Any) -> None:
            if state.global_step == 3:
                os.kill(os.getpid(), signal.SIGTERM)

    monkeypatch.setattr(headless, "ProgressLog", SigtermAt)
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_INTERRUPTED
    assert fakes["trainers"][0].saved == [3] and api.state.checkpoint["step"] == 3
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "session_ended", "step": 3}
    assert "shutting down" in no_secret(capsys)


# ------------------------------------------------------------------------------------------------ cancel / token


def test_revoked_token_exits_quietly(fakes: dict[str, Any], capsys) -> None:
    with FakeApi(FakeState(token="dtj_some_other_token_value_xxxxxxxxxx")) as api:
        assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_CANCELLED
        assert not api.state.calls("POST", "/jobs/current/fail")
    text = no_secret(capsys)
    assert "Traceback" not in text and text.count("[DocTune] WARNING") == 1


def test_cancel_from_dashboard_exits_with_cancelled(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    api.state.cancel_requested = True
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_CANCELLED
    assert "training-complete" not in " ".join(api_calls(api)) and not api.state.calls("POST", "/jobs/current/fail")
    assert "Traceback" not in no_secret(capsys)


def test_job_already_ended(api: FakeApi, fakes: dict[str, Any]) -> None:
    api.state.job_state = "completed"
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_CANCELLED


def test_malformed_token_never_echoed(fakes: dict[str, Any], capsys) -> None:
    assert headless.run(token="not-a-token-secret-123", api_url="http://127.0.0.1:9") == headless.EXIT_CANCELLED
    assert "not-a-token-secret-123" not in no_secret(capsys)


# ------------------------------------------------------------------------------------------------ failures


def test_training_error_reported_once_and_nonzero(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    fakes["behaviour"][6] = ValueError("tokenizer exploded")
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_FAILED
    fails = api.state.calls("POST", "/jobs/current/fail")
    assert [f.json() for f in fails] == [{"error": "ValueError: tokenizer exploded", "step": 6, "fatal": False}]
    assert "Failed during training" in no_secret(capsys)


def test_error_outside_training_is_reported_by_headless(fakes: dict[str, Any], capsys) -> None:
    with FakeApi(FakeState(train_mode="bogus")) as api:
        assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_FAILED
        fails = [f.json() for f in api.state.calls("POST", "/jobs/current/fail")]
    assert len(fails) == 1 and fails[0]["fatal"] is False and fails[0]["error"].startswith("loading the job:")
    no_secret(capsys)


def test_oom_before_first_step(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    fakes["behaviour"][0] = OutOfMemoryError("CUDA out of memory. Tried to allocate 2 GiB")
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_OOM
    fails = [f.json() for f in api.state.calls("POST", "/jobs/current/fail")]
    assert len(fails) == 1 and fails[0]["fatal"] is True and fails[0]["error"].startswith("out_of_memory")
    no_secret(capsys)


def test_gated_model_hint_mentions_colab(api: FakeApi, fakes: dict[str, Any]) -> None:
    fakes["load_exc"] = OSError("401 Client Error: access to model meta-llama/x is restricted (gated)")
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_FAILED
    fails = [f.json() for f in api.state.calls("POST", "/jobs/current/fail")]
    assert len(fails) == 1 and "Colab notebook" in fails[0]["error"] and "cell 5" not in fails[0]["error"]


def test_no_gpu_pauses_and_exits(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    fakes["env"] = Env(False, None, None, False, "kaggle", "3.13", None, None)
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_NO_GPU
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "no_gpu"}
    assert not api.state.calls("POST", "/jobs/current/fail")
    no_secret(capsys)


def test_evaluation_failure_still_uploads_adapter(api: FakeApi, fakes: dict[str, Any], capsys) -> None:
    fakes["gen_exc"] = RuntimeError("generation broke")
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_OK
    assert "adapter_safetensors" in api.state.artifacts and api.state.job_state == "completed"
    assert api.state.calls("POST", "/jobs/current/finish")[0].json()["metrics"] == {}
    assert "Evaluation failed" in no_secret(capsys)


# ------------------------------------------------------------------------------------------------ Kaggle runtime


def test_kaggle_pins_one_gpu_warns_non_t4_and_cleans_up(
    api: FakeApi, fakes: dict[str, Any], tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("KAGGLE_KERNEL_RUN_TYPE", "Batch")
    fakes["env"] = Env(True, "Tesla P100-PCIE-16GB", 16.0, False, "kaggle", "3.13", "2.11.0", "12.8")
    work = tmp_path / "kaggle"
    assert headless.run(token=TOKEN, api_url=api.url, workdir=work) == headless.EXIT_OK
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"
    assert not (work / "jobs" / api.state.job_id).exists()  # nothing large left in the kernel output
    text = no_secret(capsys)
    assert "platform kaggle" in text and "not a T4" in text
    assert "/content" not in text


def test_kaggle_default_workdir(monkeypatch) -> None:
    monkeypatch.delenv("DOCTUNE_WORKDIR")
    assert headless._resolve_workdir(None, "kaggle") == headless.KAGGLE_WORKDIR
    assert headless._resolve_workdir(None, "local") is None
    monkeypatch.setenv("DOCTUNE_WORKDIR", "/somewhere")
    assert headless._resolve_workdir(None, "kaggle") is None  # env.workdir() honours DOCTUNE_WORKDIR


def test_local_run_keeps_files(api: FakeApi, fakes: dict[str, Any], tmp_path: Path) -> None:
    assert headless.run(token=TOKEN, api_url=api.url) == headless.EXIT_OK
    assert (tmp_path / "work" / "jobs" / api.state.job_id / "export" / "adapter.zip").exists()


# ------------------------------------------------------------------------------------------------ entry point


def test_main_reads_env_vars(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(token: str, api_url: str) -> int:
        seen.update(token=token, api_url=api_url)
        return 7

    monkeypatch.setattr(headless, "run", fake_run)
    monkeypatch.setenv("DOCTUNE_JOB_TOKEN", f"  {TOKEN}\n")
    monkeypatch.setenv("DOCTUNE_API_URL", "https://api.example")
    assert headless.main() == 7 and seen == {"token": TOKEN, "api_url": "https://api.example"}


def test_main_missing_env_vars(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DOCTUNE_JOB_TOKEN", raising=False)
    monkeypatch.setenv("DOCTUNE_API_URL", "https://api.example")
    assert headless.main() == headless.EXIT_USAGE
    assert "DOCTUNE_JOB_TOKEN" in capsys.readouterr().err


def test_python_m_entry_point_without_torch() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("DOCTUNE_JOB_TOKEN", "DOCTUNE_API_URL")}
    code = (
        "import runpy, sys\n"
        "try:\n"
        "    runpy.run_module('doctune_nb.headless', run_name='__main__')\n"
        "except SystemExit as e:\n"
        "    assert 'torch' not in sys.modules\n"
        "    raise\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == headless.EXIT_USAGE, proc.stderr
    assert "Set DOCTUNE_JOB_TOKEN and DOCTUNE_API_URL" in proc.stderr
