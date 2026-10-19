"""Cell 8: base vs fine-tuned answers on the held-out split, quick ROUGE-L, upload generations.jsonl.

Base answers come from the same model with the LoRA adapter disabled (no second download). Greedy decoding,
max_new_tokens=256, at most `eval_max_items` items (50 for >= 7B models), seeded selection. The DocTune server
scores the generations with the user's LLM key (LLM judge); ROUGE-L here is the quick local metric.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import ui
from doctune_nb.data import Conversation, load_jsonl, render_chat, split_prompt, strip_thinking, text_tokenizer

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient, JobConfig
    from doctune_nb.train import TrainResult

GENERATION_KEYS = ("question", "reference", "base_answer", "tuned_answer")
LARGE_MODEL_PARAMS = 7e9
LARGE_MODEL_CAP = 50

# A generator turns rendered prompts into answers; `adapter=False` must answer with the base model.
Generator = Callable[[list[str], bool], list[str]]


# ----------------------------------------------------------------------------------------------- ROUGE-L

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def rouge_l(reference: str, candidate: str) -> float:
    """ROUGE-L F1 over lowercase word tokens (same definition as rouge-score's rougeL fmeasure without stemming)."""
    ref, cand = tokenize(reference), tokenize(candidate)
    if not ref or not cand:
        return 0.0
    lcs = lcs_length(ref, cand)
    if lcs == 0:
        return 0.0
    p, r = lcs / len(cand), lcs / len(ref)
    return 2 * p * r / (p + r)


# ----------------------------------------------------------------------------------------------- selection


def select_items(convs: list[Conversation], max_items: int, seed: int) -> list[Conversation]:
    if len(convs) <= max_items:
        return list(convs)
    idx = sorted(random.Random(seed).sample(range(len(convs)), max_items))
    return [convs[i] for i in idx]


def question_text(prompt_msgs: Conversation) -> str:
    users = [m["content"] for m in prompt_msgs if m["role"] == "user"]
    return users[-1] if users else ""


def write_generations(rows: list[dict[str, str]], path: str | os.PathLike[str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: str(r.get(k, "")) for k in GENERATION_KEYS}, ensure_ascii=False) + "\n")
    return path


@dataclass
class EvalResult:
    n_items: int
    rouge_l_base: float | None
    rouge_l_tuned: float | None
    generations_path: Path | None
    seconds: float

    def metrics(self) -> dict[str, float | None]:
        return {"rouge_l_base": self.rouge_l_base, "rouge_l_tuned": self.rouge_l_tuned}


# ----------------------------------------------------------------------------------------------- generation


def hf_generator(
    model: Any,
    tok: Any,
    *,
    use_unsloth: bool,
    max_new_tokens: int = 256,
    batch_size: int = 8,
    on_batch: Callable[[], None] | None = None,
) -> Generator:
    """Batched greedy generation; `adapter=False` runs inside `model.disable_adapter()`."""
    import contextlib

    import torch

    ttok = text_tokenizer(tok)
    if use_unsloth:
        from unsloth import FastLanguageModel

        FastLanguageModel.for_inference(model)
    else:
        model.eval()
    ttok.padding_side = "left"
    if ttok.pad_token is None:
        ttok.pad_token = ttok.eos_token
    device = next(model.parameters()).device

    def generate(prompts: list[str], adapter: bool) -> list[str]:
        out: list[str] = []
        ctx = contextlib.nullcontext() if adapter else model.disable_adapter()
        with ctx, torch.inference_mode():
            for i in range(0, len(prompts), batch_size):
                chunk = prompts[i : i + batch_size]
                enc = ttok(chunk, return_tensors="pt", padding=True, add_special_tokens=False).to(device)
                gen = model.generate(
                    **enc, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=ttok.pad_token_id
                )
                new = gen[:, enc["input_ids"].shape[1] :]
                out.extend(strip_thinking(t) for t in ttok.batch_decode(new, skip_special_tokens=True))
                if on_batch:
                    on_batch()
        return out

    return generate


def _param_count(model: Any) -> int:
    try:
        return int(sum(p.numel() for p in model.parameters()))
    except Exception:
        return 0


# ----------------------------------------------------------------------------------------------- run


def run(
    client: DocTuneClient,
    cfg: JobConfig,
    result: TrainResult,
    *,
    generator: Generator | None = None,
    max_items: int | None = None,
    batch_size: int = 8,
    max_new_tokens: int = 256,
) -> EvalResult:
    ui.step("Evaluation (base vs fine-tuned)")
    t0 = time.monotonic()
    cap = max_items or cfg.eval_max_items
    if generator is None and _param_count(result.model) >= LARGE_MODEL_PARAMS:
        cap = min(cap, LARGE_MODEL_CAP)
    items = select_items(load_jsonl(result.data.eval), cap, cfg.seed)
    prompts_msgs = [split_prompt(c) for c in items]
    tok = result.tokenizer
    prompts = [render_chat(tok, msgs, add_generation_prompt=True) for msgs, _ in prompts_msgs]

    last_hb = [time.monotonic()]

    def keep_alive() -> None:  # heartbeats between batches so the monitor doesn't mark the job paused
        if time.monotonic() - last_hb[0] >= cfg.heartbeat_every_seconds:
            last_hb[0] = time.monotonic()
            try:
                client.heartbeat(result.final_step, max(cfg.max_steps, result.final_step), result.final_loss)
            except Exception as exc:
                ui.warn(f"Heartbeat failed ({exc}).")

    if generator is None:
        generator = hf_generator(
            result.model,
            tok,
            use_unsloth=result.use_unsloth,
            max_new_tokens=max_new_tokens,
            batch_size=batch_size,
            on_batch=keep_alive,
        )
    ui.info(f"Answering {len(prompts)} held-out questions with the fine-tuned model...")
    tuned = generator(prompts, True)
    ui.info("Answering the same questions with the base model (adapter off)...")
    base = generator(prompts, False)

    rows = []
    for (msgs, ref), b, t in zip(prompts_msgs, base, tuned, strict=False):
        rows.append({"question": question_text(msgs), "reference": ref, "base_answer": b, "tuned_answer": t})
    n = len(rows)
    rl_base = round(sum(rouge_l(r["reference"], r["base_answer"]) for r in rows) / n, 4) if n else None
    rl_tuned = round(sum(rouge_l(r["reference"], r["tuned_answer"]) for r in rows) / n, 4) if n else None
    path = write_generations(rows, result.workdir / "eval" / "generations.jsonl")
    gen_path: Path | None = path
    try:
        client.upload_artifact("eval_generations", path)
    except Exception as exc:
        ui.warn(f"Could not upload the evaluation answers ({exc}). The adapter upload in the next cell still works.")
        gen_path = None
    if result.use_unsloth:
        try:
            from unsloth import FastLanguageModel

            FastLanguageModel.for_training(result.model)
        except Exception:
            pass
    res = EvalResult(n, rl_base, rl_tuned, gen_path, round(time.monotonic() - t0, 1))
    ui.info(
        f"ROUGE-L vs reference answers: base {rl_base}, fine-tuned {rl_tuned} ({n} questions, "
        f"{res.seconds:.0f} s). DocTune will also score them with your LLM judge."
    )
    for r in rows[:2]:
        ui.info(f"Q: {r['question'][:200]}\n  base:  {r['base_answer'][:300]}\n  tuned: {r['tuned_answer'][:300]}")
    return res
