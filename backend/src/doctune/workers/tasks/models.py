"""Model-side background work: adapter -> GGUF for the playground, and evaluation scoring."""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

import structlog
from celery import Task
from sqlalchemy import select

from doctune.core import events
from doctune.core.config import get_settings
from doctune.core.db import sync_session
from doctune.core.storage import get_storage
from doctune.llm.client import LLMError, NoProviders, ProvidersExhausted
from doctune.llm.prompts import EvalOut, eval_messages
from doctune.models.generation import DatasetVersion, StyleConfig
from doctune.models.project import Project
from doctune.models.training import Artifact, ArtifactKind, Checkpoint, EvalState, Evaluation, TrainingJob
from doctune.services import generation as gen
from doctune.workers.celery_app import app

log = structlog.get_logger()
ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors")
ARTIFACT_TTL = timedelta(days=14)


class ConvertError(Exception):
    pass


def extract_adapter(zip_bytes: bytes, dest: Path) -> Path:
    """Unpack only the adapter files (from an adapter zip or a full checkpoint zip)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = {Path(n).name: n for n in z.namelist() if Path(n).name in ADAPTER_FILES}
        if set(names) != set(ADAPTER_FILES):
            raise ConvertError("zip does not contain a LoRA adapter")
        for short, full in names.items():
            info = z.getinfo(full)
            if info.file_size > 2 * 1024**3:
                raise ConvertError("adapter file too large")
            (dest / short).write_bytes(z.read(full))
    return dest


def fetch_base_config(base_model_id: str, cache_dir: Path) -> Path:
    """Config + tokenizer of the base model (small files only) — enough for convert_lora_to_gguf.py."""
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            base_model_id,
            allow_patterns=["*.json", "tokenizer*", "*.model", "*.txt"],
            cache_dir=str(cache_dir),
        )
    )


def run_convert(adapter_dir: Path, base_dir: Path, out_file: Path) -> None:
    settings = get_settings()
    llama = settings.llama_cpp_dir
    if llama is None:
        raise ConvertError("LLAMA_CPP_DIR is not configured")
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            settings.llama_convert_python or sys.executable,
            str(llama / "convert_lora_to_gguf.py"),
            str(adapter_dir),
            "--base",
            str(base_dir),
            "--outtype",
            "f16",
            "--outfile",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if proc.returncode != 0 or not out_file.exists():
        raise ConvertError(proc.stderr[-1500:] or "conversion failed")


@app.task(name="doctune.workers.tasks.models.convert_adapter", soft_time_limit=1200, time_limit=1260, max_retries=2)
def convert_adapter(job_id: str, source: str = "final") -> str | None:
    """Convert the final adapter (or the latest checkpoint's adapter) to a GGUF LoRA for llama.cpp."""
    jid = uuid.UUID(job_id)
    if get_settings().llama_cpp_dir is None:
        log.info("adapter_convert_skipped", reason="LLAMA_CPP_DIR not configured; playground unavailable")
        return None
    storage = get_storage()
    with sync_session() as db:
        job = db.get(TrainingJob, jid)
        if job is None:
            return None
        if source == "checkpoint":
            ckpt = db.get(Checkpoint, jid)
            if ckpt is None:
                return None
            src_key, out_key, kind, meta = (
                ckpt.storage_key,
                f"j/{jid}/checkpoint/adapter.gguf",
                ArtifactKind.checkpoint_gguf,
                {"step": ckpt.step},
            )
        else:
            src = db.scalar(
                select(Artifact).where(
                    Artifact.job_id == jid, Artifact.kind == ArtifactKind.adapter_safetensors, Artifact.uploaded
                )
            )
            if src is None:
                return None
            src_key, out_key, kind, meta = (
                src.storage_key,
                f"j/{jid}/adapter/adapter.gguf",
                ArtifactKind.adapter_gguf,
                {},
            )
        base_model_id = job.base_model_id
        project_id = job.project_id

    work = Path(tempfile.mkdtemp(prefix="convert-"))
    try:
        adapter_dir = work / "adapter"
        adapter_dir.mkdir()
        extract_adapter(storage.read_bytes(src_key), adapter_dir)
        config = json.loads((adapter_dir / "adapter_config.json").read_text())
        base_name = str(config.get("base_model_name_or_path", ""))
        if base_name and base_name.split("/")[-1].lower().replace("-bnb-4bit", "") not in base_model_id.lower():
            raise ConvertError(f"adapter was trained on {base_name}, expected {base_model_id}")
        base_dir = fetch_base_config(base_model_id, get_settings().llama_models_dir / "hf-cache")
        out_file = work / "adapter.gguf"
        run_convert(adapter_dir, base_dir, out_file)
        data = out_file.read_bytes()
        storage.write_bytes(out_key, data)
    except ConvertError as exc:
        log.warning("adapter_convert_failed", job_id=job_id, source=source, error=str(exc)[:300])
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with sync_session() as db:
        existing = db.scalar(select(Artifact).where(Artifact.job_id == jid, Artifact.kind == kind))
        art = existing or Artifact(job_id=jid, kind=kind, storage_key=out_key)
        art.size_bytes, art.uploaded, art.meta = len(data), True, meta
        art.expires_at = datetime.now(UTC) + ARTIFACT_TTL
        db.add(art)
        db.commit()
    events.publish(project_id, "progress", {"phase": "convert", "source": source, "state": "done"})
    return out_key


# ---------------- evaluation ----------------


def _summary(scores: list[tuple[int, int]]) -> dict[str, float]:
    if not scores:
        return {"correctness": 0.0, "style": 0.0, "overall": 0.0}
    c, s = mean(x for x, _ in scores), mean(y for _, y in scores)
    return {"correctness": round(c, 2), "style": round(s, 2), "overall": round((c + s) / 2, 2)}


def _key(text: str) -> str:
    return " ".join(text.lower().split())[:500]


def _add_conversation_context(items: list[dict[str, Any]], eval_key: str) -> None:
    """The notebook sends only the last question; give the judge the turns before it so follow-ups make sense."""
    context: dict[tuple[str, str], str] = {}
    for line in get_storage().read_bytes(eval_key).decode().splitlines():
        if not line.strip():
            continue
        turns = [m for m in json.loads(line).get("messages", []) if m.get("role") in ("user", "assistant")]
        if len(turns) < 4:
            continue
        earlier = "\n".join(f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in turns[:-2])
        context[(_key(turns[-2]["content"]), _key(turns[-1]["content"]))] = earlier[-1500:]
    for it in items:
        found = context.get((_key(it["question"]), _key(it["reference"])))
        if found:
            it["context"] = found


@app.task(
    bind=True,
    name="doctune.workers.tasks.models.score_evaluation",
    soft_time_limit=1800,
    time_limit=1860,
    max_retries=24,
)
def score_evaluation(self: Task, job_id: str) -> str:  # type: ignore[type-arg]
    jid = uuid.UUID(job_id)
    with sync_session() as db:
        evaluation = db.scalar(select(Evaluation).where(Evaluation.job_id == jid))
        job = db.get(TrainingJob, jid)
        art = db.scalar(
            select(Artifact).where(
                Artifact.job_id == jid, Artifact.kind == ArtifactKind.eval_generations, Artifact.uploaded
            )
        )
        if evaluation is None or job is None or art is None or evaluation.state == EvalState.done:
            return "skipped"
        project = db.get(Project, job.project_id)
        assert project is not None
        style = db.get(StyleConfig, project.style_id) if project.style_id else None
        items: list[dict[str, Any]] = []
        for line in get_storage().read_bytes(art.storage_key).decode().splitlines():
            if line.strip():
                row = json.loads(line)
                items.append(
                    {k: str(row.get(k, ""))[:3000] for k in ("question", "reference", "base_answer", "tuned_answer")}
                )
        items = items[:100]
        version = db.get(DatasetVersion, job.dataset_version_id)
        if version is not None and version.dataset_format == "multi_turn":
            _add_conversation_context(items, version.eval_key)
        evaluation.state, evaluation.n_items = EvalState.scoring, len(items)
        db.commit()
        events.publish(project.id, "progress", {"phase": "eval", "state": "scoring"})

        llm = gen.make_llm(db, project, job.user_id)
        base: list[tuple[int, int]] = []
        tuned: list[tuple[int, int]] = []
        per_item: list[dict[str, Any]] = []
        try:
            for start in range(0, len(items), 8):
                batch = items[start : start + 8]
                payload = [{"id": f"e{i + 1}", **it} for i, it in enumerate(batch)]
                result = llm.complete_json(
                    eval_messages(style.description if style else "", payload),
                    EvalOut,
                    max_tokens=80 * len(batch) + 200,
                    temperature=0.0,
                )
                by_id = {s.id: s for s in result.data.scores}
                for i, it in enumerate(batch):
                    s = by_id.get(f"e{i + 1}")
                    if s is None:
                        continue
                    base.append((s.a_correctness, s.a_style))
                    tuned.append((s.b_correctness, s.b_style))
                    gain = (s.b_correctness + s.b_style) - (s.a_correctness + s.a_style)
                    per_item.append(
                        {
                            **it,
                            "base_score": s.a_correctness + s.a_style,
                            "tuned_score": s.b_correctness + s.b_style,
                            "gain": gain,
                        }
                    )
        except ProvidersExhausted as exc:
            db.rollback()
            raise self.retry(countdown=min(int(exc.retry_after) + 30, 3600), exc=exc) from exc
        except NoProviders:
            evaluation.state, evaluation.error = (
                EvalState.failed,
                "Connect an API key in Settings to score the evaluation.",
            )
            db.commit()
            return "no_providers"
        except LLMError as exc:
            evaluation.state, evaluation.error = EvalState.failed, f"Scoring failed: {exc}"[:500]
            db.commit()
            return "failed"

        per_item.sort(key=lambda r: -r["gain"])
        samples = per_item[:10] + [r for r in per_item[-2:] if r not in per_item[:10]]
        evaluation.base_scores, evaluation.tuned_scores = _summary(base), _summary(tuned)
        evaluation.samples = samples
        evaluation.metrics = job.metrics
        evaluation.state = EvalState.done
        db.commit()
        events.publish(project.id, "progress", {"phase": "eval", "state": "done"})
        return "done"
