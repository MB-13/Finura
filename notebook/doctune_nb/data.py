"""Dataset download (pre-signed URL + sha256), chat JSONL parsing and chat-template rendering.

The chat template is always rendered in non-thinking mode (`enable_thinking=False`) for Qwen3/3.5, and the same
rendering is used for training, evaluation and the exported Ollama template.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doctune_nb import ui
from doctune_nb.api import DocTuneError, sha256_file

if TYPE_CHECKING:
    from doctune_nb.api import DocTuneClient, JobConfig

Message = dict[str, str]
Conversation = list[Message]

ROLES = {"system", "user", "assistant"}


class DatasetError(DocTuneError):
    pass


@dataclass
class DatasetFiles:
    train: Path
    eval: Path


def download_dataset(client: DocTuneClient, cfg: JobConfig, root: str | os.PathLike[str]) -> DatasetFiles:
    """Download train/eval JSONL once per session; reuse local copies whose sha256 still matches."""
    root = Path(root) / "data"
    root.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, url, sha in (
        ("train", cfg.dataset.train_url, cfg.dataset.sha256_train),
        ("eval", cfg.dataset.eval_url, cfg.dataset.sha256_eval),
    ):
        path = root / f"{name}.jsonl"
        if path.exists() and sha256_file(path) == sha:
            out[name] = path
            continue
        out[name] = client.download_signed(url, path, sha256=sha, desc=f"{name} dataset")
    ui.info(f"Dataset ready: {cfg.dataset.train_count} training pairs, {cfg.dataset.eval_count} held out (verified).")
    return DatasetFiles(train=out["train"], eval=out["eval"])


def load_jsonl(path: str | os.PathLike[str]) -> list[Conversation]:
    """Parse chat JSONL ({"messages": [{role, content}, ...]}) and validate the structure."""
    convs: list[Conversation] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"Dataset line {lineno} is not valid JSON.") from exc
            msgs = row.get("messages") if isinstance(row, dict) else None
            if not isinstance(msgs, list) or not msgs:
                raise DatasetError(f"Dataset line {lineno} has no messages.")
            clean: Conversation = []
            for m in msgs:
                if not isinstance(m, dict) or m.get("role") not in ROLES or not isinstance(m.get("content"), str):
                    raise DatasetError(f"Dataset line {lineno} has an invalid message.")
                clean.append({"role": m["role"], "content": m["content"]})
            if clean[-1]["role"] != "assistant":
                raise DatasetError(f"Dataset line {lineno} does not end with an assistant answer.")
            convs.append(clean)
    if not convs:
        raise DatasetError("The dataset is empty.")
    return convs


def text_tokenizer(tok: Any) -> Any:
    """Unsloth may return a processor for multimodal models (Qwen3.5); the text tokenizer is `.tokenizer`."""
    return getattr(tok, "tokenizer", tok)


def render_chat(tok: Any, messages: Conversation, *, add_generation_prompt: bool = False) -> str:
    """apply_chat_template with thinking disabled (falls back for templates without enable_thinking)."""
    ttok = text_tokenizer(tok)
    try:
        return ttok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=add_generation_prompt, enable_thinking=False
        )
    except TypeError:
        return ttok.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt)


def split_prompt(conv: Conversation) -> tuple[Conversation, str]:
    """(messages up to the last assistant turn, reference answer)."""
    return conv[:-1], conv[-1]["content"]


# (instruction_part, response_part) for train_on_responses_only, per chat format
CHAT_MARKERS: dict[str, tuple[str, str]] = {
    "chatml": ("<|im_start|>user\n", "<|im_start|>assistant\n"),  # Qwen2/3/3.5
    "llama3": ("<|start_header_id|>user<|end_header_id|>\n\n", "<|start_header_id|>assistant<|end_header_id|>\n\n"),
    "gemma": ("<start_of_turn>user\n", "<start_of_turn>model\n"),
    "phi3": ("<|user|>\n", "<|assistant|>\n"),
    "mistral": ("[INST]", "[/INST]"),
}


def detect_chat_format(tok: Any) -> str | None:
    """Render a probe conversation and look for known role markers."""
    probe = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    try:
        text = render_chat(tok, probe)
    except Exception:
        return None
    for name, (inst, resp) in CHAT_MARKERS.items():
        if inst in text and resp in text:
            return name
    return None


def format_conversations(tok: Any, convs: list[Conversation]) -> list[str]:
    return [render_chat(tok, c) for c in convs]


def to_hf_dataset(texts: list[str]) -> Any:
    from datasets import Dataset

    return Dataset.from_dict({"text": texts})


_THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Remove an (empty) <think> block that non-thinking Qwen output may still start with."""
    return _THINK.sub("", text).strip()
