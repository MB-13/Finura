"""CPU smoke test: the real training loop (transformers + PEFT + TRL, no Unsloth) against the fake API.

Uninterrupted run vs. interrupted (Ctrl-C at step 4 -> checkpoint upload -> pause) + resumed run in a fresh
"session": the resumed losses must match. Then evaluation (real generation, adapter on/off) and the adapter upload.

Skipped by default. Run with:  uv pip install -e '.[smoke]' (CPU torch, see README) && uv run pytest --run-slow -m slow
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fake_api import FakeApi, FakeState

from doctune_nb import evaluate, export, train, ui
from doctune_nb.api import DocTuneClient
from doctune_nb.callbacks import _Callback
from doctune_nb.env import Env

pytestmark = pytest.mark.slow

TINY = "trl-internal-testing/tiny-Qwen3ForCausalLM"  # real Qwen3 chat template, ~10 MB
CPU = Env(False, None, None, False, "local", "3.12", None, None)
MAX_STEPS = 8


class Recorder(_Callback):
    def __init__(self, stop_at: int | None = None) -> None:
        self.losses: dict[int, float] = {}
        self.grad_norms: dict[int, float] = {}
        self.stop_at = stop_at

    def on_log(self, args: Any, state: Any, control: Any, logs: dict | None = None, **kw: Any) -> None:
        if logs and "loss" in logs:
            self.losses[state.global_step] = float(logs["loss"])
        if logs and "grad_norm" in logs:
            self.grad_norms[state.global_step] = float(logs["grad_norm"])

    def on_step_end(self, args: Any, state: Any, control: Any, **kw: Any) -> None:
        if self.stop_at is not None and state.global_step == self.stop_at:
            raise KeyboardInterrupt


def state() -> FakeState:
    return FakeState(
        base_model_id=TINY,
        max_steps=MAX_STEPS,
        seed=42,
        hyperparams={"batch_size": 2, "grad_accum": 1, "lora_r": 8, "lora_alpha": 16, "max_seq_len": 512},
        train_pairs=[(f"What is fact {i}?", f"Fact {i} is that lamp {i} glows blue.") for i in range(16)],
        eval_pairs=[(f"What is fact {i}?", f"Fact {i} is that lamp {i} glows blue.") for i in range(3)],
        job_id="00000000-0000-0000-0000-000000000001",
    )


def test_cpu_train_interrupt_resume_eval_export(tmp_path: Path) -> None:
    # 1) reference: uninterrupted run
    with FakeApi(state()) as api0:
        c0 = DocTuneClient(api0.state.token, api0.url, sleep=lambda s: None)
        ref = Recorder()
        r0 = train.run(c0, c0.config(), CPU, workdir=tmp_path / "ref", use_unsloth=False, extra_callbacks=[ref])
        assert r0.final_step == MAX_STEPS and r0.chat_format == "chatml"

    with FakeApi(state()) as api:
        client = DocTuneClient(api.state.token, api.url, sleep=lambda s: None)
        cfg = client.config()

        # 2) session 1: Ctrl-C at step 4 -> checkpoint written + uploaded -> pause(user_stopped)
        with pytest.raises(ui.StopNotebook, match="You stopped training at 50%"):
            train.run(client, cfg, CPU, workdir=tmp_path / "s1", use_unsloth=False, extra_callbacks=[Recorder(4)])
        assert api.state.checkpoint and api.state.checkpoint["step"] == 4
        with zipfile.ZipFile(io.BytesIO(api.state.storage["ckpt/latest.zip"])) as z:
            names = set(z.namelist())
        for f in (
            "adapter_model.safetensors",
            "adapter_config.json",
            "optimizer.pt",
            "scheduler.pt",
            "trainer_state.json",
            "doctune_meta.json",
        ):
            assert f in names, names
        assert any(n.startswith("rng_state") for n in names)
        assert api.state.calls("POST", "/jobs/current/pause")[-1].json() == {"reason": "user_stopped", "step": 4}

        # 3) session 2 (fresh workdir): downloads + verifies the checkpoint and resumes at step 5
        rec = Recorder()
        res = train.run(client, cfg, CPU, workdir=tmp_path / "s2", use_unsloth=False, extra_callbacks=[rec])
        assert res.final_step == MAX_STEPS
        assert min(rec.losses) == 5
        assert api.state.calls("POST", "/jobs/current/start")[-1].json()["resumed_from_step"] == 4
        for step in range(5, MAX_STEPS + 1):
            # the random tiny model's loss barely moves, so grad norms are the sharper check of a faithful resume
            assert rec.losses[step] == pytest.approx(ref.losses[step], rel=1e-3), (step, rec.losses, ref.losses)
            assert rec.grad_norms[step] == pytest.approx(ref.grad_norms[step], rel=1e-3), (step, rec.grad_norms)
        assert len(set(ref.grad_norms.values())) > 1  # not a degenerate comparison
        assert api.state.calls("POST", "/jobs/current/training-complete")

        # 4) evaluation: real greedy generation with the adapter on and off
        ev = evaluate.run(client, cfg, res, max_new_tokens=8, batch_size=2)
        assert ev.n_items == 3 and ev.generations_path is not None
        rows = [json.loads(x) for x in api.state.artifacts["eval_generations"]["data"].decode().splitlines()]
        assert len(rows) == 3 and set(rows[0]) == {"question", "reference", "base_answer", "tuned_answer"}

        # 5) adapter first, then finish
        export.upload_adapter_and_finish(client, cfg, res, ev, license_fetcher=lambda r, t: "LICENSE")
        with zipfile.ZipFile(io.BytesIO(api.state.artifacts["adapter_safetensors"]["data"])) as z:
            names = set(z.namelist())
            assert {"adapter_model.safetensors", "adapter_config.json", "README.md", "LICENSE"} <= names
            assert json.loads(z.read("adapter_config.json"))["base_model_name_or_path"] == TINY
        assert api.state.job_state == "completed"
