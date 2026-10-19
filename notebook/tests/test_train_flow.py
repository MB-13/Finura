"""train.run orchestration with the model/trainer replaced by fakes (no torch): start/resume, Ctrl-C, OOM, errors,
cancel, completion - and the API calls each one makes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import ChatmlTokenizer
from fake_api import FakeApi
from test_callbacks import write_checkpoint

from doctune_nb import train, ui
from doctune_nb.api import DocTuneClient
from doctune_nb.env import Env

GPU = Env(True, "Tesla T4", 15.6, False, "colab", "3.12", "2.11.0", "13.0")


class OutOfMemoryError(RuntimeError):
    pass


class FakeTrainer:
    """Calls the callbacks like transformers.Trainer would, then runs `behaviour` at a given step."""

    def __init__(self, out_dir: Path, callbacks: list[Any], max_steps: int, behaviour: dict[int, Any], bs: int):
        self.args = SimpleNamespace(output_dir=str(out_dir))
        self.state = SimpleNamespace(global_step=0, max_steps=max_steps)
        self.callbacks, self.behaviour, self.bs = callbacks, behaviour, bs
        self.model = "peft-model"
        self.resumed_from: str | None = None
        self.saved: list[int] = []

    def _event(self, name: str, **kw: Any) -> SimpleNamespace:
        control = SimpleNamespace(should_save=False, should_training_stop=False)
        for cb in self.callbacks:
            getattr(cb, name)(self.args, self.state, control, **kw)
        return control

    def _save_checkpoint(self, model: Any, trial: Any) -> None:
        write_checkpoint(Path(self.args.output_dir), self.state.global_step)
        self.saved.append(self.state.global_step)

    def train(self, resume_from_checkpoint: str | None = None) -> Any:
        self.resumed_from = resume_from_checkpoint
        if resume_from_checkpoint:
            self.state.global_step = int(resume_from_checkpoint.rsplit("-", 1)[-1])
        self._event("on_train_begin")
        while self.state.global_step < self.state.max_steps:
            action = self.behaviour.get((self.state.global_step, self.bs)) or self.behaviour.get(self.state.global_step)
            if action is not None:
                raise action
            self.state.global_step += 1
            self._event("on_log", logs={"loss": 1.0 / self.state.global_step, "learning_rate": 1e-4})
            ctl = self._event("on_step_end")
            if ctl.should_training_stop:
                break
            if self.state.global_step == self.state.max_steps:
                self._save_checkpoint(None, None)
                self._event("on_save")
        self._event("on_train_end")
        return SimpleNamespace(training_loss=0.5, metrics={"train_runtime": 12.0})


@pytest.fixture
def patched(monkeypatch, tmp_path: Path):
    """Replace model loading + trainer construction; returns a dict to set behaviours and inspect trainers."""
    ctx: dict[str, Any] = {"behaviour": {}, "trainers": [], "load_exc": None}

    def load_model(cfg, **kw):
        if ctx["load_exc"]:
            raise ctx["load_exc"]
        return "model", ChatmlTokenizer()

    def build_trainer(model, tok, ds, cfg, out_dir, callbacks, **kw):
        t = FakeTrainer(out_dir, callbacks, cfg.max_steps, ctx["behaviour"], kw["batch_size"])
        t.kw = kw
        ctx["trainers"].append(t)
        return t

    monkeypatch.setattr(train, "load_model", load_model)
    monkeypatch.setattr(train, "build_trainer", build_trainer)
    monkeypatch.setattr(train, "to_hf_dataset", lambda texts: texts)
    return ctx


def run(client: DocTuneClient, tmp_path: Path) -> train.TrainResult:
    return train.run(client, client.config(), GPU, workdir=tmp_path, use_unsloth=False)


def posts(api: FakeApi) -> list[str]:
    return [r.path.rsplit("/", 1)[-1] for r in api.state.requests if r.method == "POST"]


def test_happy_path(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    res = run(client, tmp_path)
    assert res.final_step == 10 and res.final_loss == pytest.approx(0.1) and res.runtime_s == 12.0
    p = posts(api)
    assert p[0] == "start" and p[-1] == "training-complete" and "heartbeat" in p and "complete" in p
    start = api.state.calls("POST", "/jobs/current/start")[0].json()
    assert start["resumed_from_step"] is None if "resumed_from_step" in start else True
    assert start["runtime"]["gpu_name"] == "Tesla T4"
    assert api.state.checkpoint["step"] == 10  # final checkpoint uploaded
    tc = api.state.calls("POST", "/jobs/current/training-complete")[0].json()
    assert tc == {"final_step": 10, "final_loss": pytest.approx(0.1), "train_runtime_s": 12.0}


def test_ctrl_c_saves_uploads_and_pauses(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    patched["behaviour"][4] = KeyboardInterrupt()
    with pytest.raises(ui.StopNotebook, match="You stopped training at 40%"):
        run(client, tmp_path)
    assert patched["trainers"][0].saved == [4]
    assert api.state.checkpoint["step"] == 4
    assert api.state.calls("POST", "/jobs/current/pause")[0].json() == {"reason": "user_stopped", "step": 4}
    assert "training-complete" not in posts(api)

    # rerun all cells (new session = new workdir): resumes from the uploaded step-4 checkpoint
    patched["behaviour"].clear()
    res = run(client, tmp_path / "session2")
    t = patched["trainers"][-1]
    assert t.resumed_from.endswith("checkpoint-4") and res.final_step == 10
    assert api.state.calls("POST", "/jobs/current/start")[-1].json()["resumed_from_step"] == 4


def test_oom_at_step_zero_is_fatal(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    patched["behaviour"][0] = OutOfMemoryError("CUDA out of memory. Tried to allocate 2 GiB")
    with pytest.raises(ui.StopNotebook, match="smaller model"):
        run(client, tmp_path)
    fail = api.state.calls("POST", "/jobs/current/fail")[0].json()
    assert fail["fatal"] is True and fail["error"].startswith("out_of_memory") and fail["step"] == 0


def test_oom_mid_run_retries_once_with_half_batch(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    write_checkpoint(tmp_path / "jobs" / api.state.job_id / "ckpt", 3)  # a local checkpoint from earlier
    patched["behaviour"][(5, 2)] = OutOfMemoryError("CUDA out of memory")
    res = run(client, tmp_path)
    first, second = patched["trainers"]
    assert first.kw["batch_size"] == 2 and second.kw["batch_size"] == 1 and second.kw["grad_accum"] == 2
    assert second.resumed_from.endswith("checkpoint-3") and res.final_step == 10
    assert "fail" not in posts(api)


def test_other_error_reports_nonfatal_fail(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    patched["behaviour"][6] = ValueError("tokenizer exploded")
    with pytest.raises(ValueError):
        run(client, tmp_path)
    fail = api.state.calls("POST", "/jobs/current/fail")[0].json()
    assert fail == {"error": "ValueError: tokenizer exploded", "step": 6, "fatal": False}


def test_gated_model_hint(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    patched["load_exc"] = OSError("401 Client Error: access to model meta-llama/x is restricted (gated)")
    with pytest.raises(OSError):
        run(client, tmp_path)
    assert "Hugging Face token" in api.state.calls("POST", "/jobs/current/fail")[0].json()["error"]


def test_cancel_from_dashboard(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    api.state.cancel_requested = True
    with pytest.raises(ui.StopNotebook, match="cancelled"):
        run(client, tmp_path)
    assert "training-complete" not in posts(api)


def test_job_already_ended(api: FakeApi, client: DocTuneClient, tmp_path: Path, patched) -> None:
    api.state.job_state = "completed"
    with pytest.raises(ui.StopNotebook, match="already ended"):
        run(client, tmp_path)


def test_warmup_and_args_helper() -> None:
    assert train.warmup_steps(0.05, 100) == 5 and train.warmup_steps(0.05, 10) == 1

    from dataclasses import dataclass

    @dataclass
    class Args:
        a: int = 0

    assert train.make_dataclass_args(Args, {"a": 1, "unknown": 2}).a == 1
