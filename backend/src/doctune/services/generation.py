"""Dataset generation engine (worker side, synchronous).

A run is split into units (one per chunk). Each unit generates pairs, then judges them. Units run
a few at a time ("lanes") so a user stays within free-tier limits; when every provider is out of
quota the run waits (`waiting_quota`) and the beat task resumes it.
"""

import difflib
import math
import random
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from doctune.core import events
from doctune.core.db import sync_session
from doctune.embeddings.encoder import cosine, get_encoder
from doctune.llm.client import LLMClient, build_chain
from doctune.llm.prompts import (
    ConversationGenOut,
    GenerationOut,
    InstructionGenOut,
    JudgeOut,
    StyleSpec,
    generation_messages,
    judge_messages,
)
from doctune.models.document import Chunk
from doctune.models.generation import (
    DatasetPair,
    GenerationRun,
    GenerationUnit,
    GenKind,
    GenState,
    KeyStatus,
    PairSplit,
    ProviderKey,
    UnitState,
)
from doctune.models.project import Project
from doctune.parsing.chunker import count_tokens
from doctune.services import formats

log = structlog.get_logger()

LANES = 3
OVERGENERATE = 1.3
MAX_PER_CHUNK = formats.MAX_PER_CHUNK["qa_chat"]
KEEP_MIN_SCORE = 4
DUPLICATE_COSINE = 0.92
COPY_RATIO = 0.8
# "use what's generated so far" needs enough judged pairs to train on and still hold some out for evaluation
FINISH_EARLY_MIN_PAIRS = 20


# ---------------- planning ----------------


@dataclass
class Plan:
    chunk_ids: list[uuid.UUID]
    pairs_per_chunk: int
    supported_pairs: int


AVOID_LIMIT = 40  # existing questions shown to the generator per chunk; keeps the prompt small


def existing_questions(db: Session, run: GenerationRun, chunk_id: uuid.UUID) -> list[str]:
    """Questions earlier full runs of this project already generated from this chunk (kept or not)."""
    return list(
        db.scalars(
            select(DatasetPair.question)
            .join(GenerationRun, GenerationRun.id == DatasetPair.run_id)
            .where(
                DatasetPair.project_id == run.project_id,
                DatasetPair.chunk_id == chunk_id,
                DatasetPair.run_id != run.id,
                GenerationRun.kind == GenKind.full,
            )
            .order_by(DatasetPair.created_at.desc())
            .limit(AVOID_LIMIT)
        )
    )


def plan_run(chunk_ids: list[uuid.UUID], target_pairs: int, seed: str, max_per_chunk: int = MAX_PER_CHUNK) -> Plan:
    """Pick chunks and pairs-per-chunk so we generate ~target × 1.3 pairs before filtering."""
    needed = math.ceil(target_pairs * OVERGENERATE)
    if not chunk_ids:
        return Plan([], 0, 0)
    per_chunk = min(max_per_chunk, max(1, math.ceil(needed / len(chunk_ids))))
    chosen = list(chunk_ids)
    if per_chunk == 1 and len(chunk_ids) > needed:
        # more chunks than needed: sample evenly across the documents (ids are in document order)
        step = len(chunk_ids) / needed
        chosen = [chunk_ids[int(i * step)] for i in range(needed)]
    random.Random(seed).shuffle(chosen)  # noqa: S311 - not security sensitive
    return Plan(chosen, per_chunk, len(chosen) * per_chunk)


# ---------------- LLM helpers ----------------


def _mark_key(key_id: uuid.UUID, status: KeyStatus, reset_at: datetime | None = None) -> None:
    with sync_session() as db:
        key = db.get(ProviderKey, key_id)
        if key is not None:
            key.status = status
            key.quota_reset_at = reset_at
            db.commit()


def make_llm(db: Session, project: Project, user_id: uuid.UUID, **overrides: object) -> LLMClient:
    chain = build_chain(db, user_id, (project.gen_provider, project.gen_model))

    def notice(msg: str) -> None:
        events.publish(project.id, "notice", {"level": "info", "text": msg})

    return LLMClient(
        chain,
        user_id=user_id,
        on_notice=notice,
        on_key_invalid=lambda kid: _mark_key(kid, KeyStatus.invalid),
        on_key_quota=lambda kid, until: _mark_key(kid, KeyStatus.quota_exhausted, until),
        **overrides,  # type: ignore[arg-type]
    )


def _norm(text_: str) -> str:
    return re.sub(r"\W+", " ", text_.lower()).strip()


Generated = tuple[str, str, dict[str, object] | None]  # question, answer, record (see formats)


def _records(result: BaseModel, n: int) -> list[formats.Record]:
    """The model's items as records; malformed items are skipped one by one."""
    raw: list[dict[str, object]] = []
    if isinstance(result, InstructionGenOut):
        raw = [{"format": "instruction", **it.model_dump()} for it in result.items[: n + 2]]
    elif isinstance(result, ConversationGenOut):
        raw = [
            {
                "format": "multi_turn",
                "messages": [{"role": t.role.strip().lower(), "content": t.content.strip()} for t in c.messages],
            }
            for c in result.conversations[: n + 2]
        ]
    elif isinstance(result, GenerationOut):
        raw = [{"format": "qa_chat", "question": p.question, "answer": p.answer} for p in result.pairs[: n + 2]]
    out: list[formats.Record] = []
    for item in raw:
        try:
            rec = _RECORD.validate_python(item)
        except ValidationError:
            continue
        if isinstance(rec, formats.ConversationRecord) and (
            count_tokens(" ".join(t.content for t in rec.messages)) > formats.MULTI_TURN_MAX_TOKENS
        ):
            continue
        out.append(rec)
    return out


_RECORD: TypeAdapter[formats.Record] = TypeAdapter(formats.PairRecord)
_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {"instruction": InstructionGenOut, "multi_turn": ConversationGenOut}


def generate_pairs(
    llm: LLMClient, style: StyleSpec, chunk_text: str, n: int, avoid: list[str] | None = None
) -> tuple[list[Generated], int, int]:
    """Examples in the style's dataset format. `avoid`: opening questions already asked about this chunk (a
    "generate more" pass), so new examples cover new ground."""
    fmt = style.dataset_format
    schema = _OUTPUT_SCHEMAS.get(fmt, GenerationOut)
    result = llm.complete_json(
        generation_messages(style, chunk_text, n, avoid), schema, max_tokens=formats.max_tokens(fmt, n)
    )
    examples = [e["output"] for e in style.examples]
    seen: set[str] = {_norm(q) for q in avoid or []}
    items: list[Generated] = []
    for rec in _records(result.data, n):
        question, answer, record = formats.columns(rec)
        key = formats.dedupe_key(fmt, question, record)
        if not question or not answer or key in seen:
            continue
        # drop examples that copy a style example instead of matching its style
        if any(
            difflib.SequenceMatcher(None, a, ex).ratio() > COPY_RATIO
            for a in formats.assistant_texts(fmt, question, answer, record)
            for ex in examples
        ):
            continue
        seen.add(key)
        items.append((question, answer, record))
    return items, result.tokens_in, result.tokens_out


def judge(llm: LLMClient, style: StyleSpec, chunk_text: str, pairs: list[DatasetPair]) -> tuple[int, int]:
    """Score pairs in place. Pairs the judge skipped are dropped as `judge_failed`."""
    if not pairs:
        return 0, 0
    ids = {f"p{i + 1}": p for i, p in enumerate(pairs)}
    payload = [
        {"id": k, "text": formats.judge_text(p.dataset_format, p.question, p.answer, p.record)} for k, p in ids.items()
    ]
    result = llm.complete_json(judge_messages(style, chunk_text, payload), JudgeOut, max_tokens=60 * len(pairs) + 200)
    scored = {s.id: s for s in result.data.scores}
    for key, pair in ids.items():
        s = scored.get(key)
        if s is None:
            pair.kept, pair.dropped_reason = False, "judge_failed"
            continue
        pair.judge_correctness, pair.judge_style, pair.judge_reason = s.correctness, s.style, s.reason[:300]
        ok = s.correctness >= KEEP_MIN_SCORE and s.style >= KEEP_MIN_SCORE
        pair.kept, pair.dropped_reason = (True, None) if ok else (False, "judge_low")
    return result.tokens_in, result.tokens_out


def add_tokens(db: Session, run_id: uuid.UUID, tokens_in: int, tokens_out: int, generated: int = 0) -> None:
    db.execute(
        update(GenerationRun)
        .where(GenerationRun.id == run_id)
        .values(
            tokens_in=GenerationRun.tokens_in + tokens_in,
            tokens_out=GenerationRun.tokens_out + tokens_out,
            pairs_generated=GenerationRun.pairs_generated + generated,
            updated_at=func.now(),
        )
    )


# ---------------- unit scheduling ----------------


def claim_pending_units(db: Session, run_id: uuid.UUID, limit: int) -> list[uuid.UUID]:
    rows = (
        db.execute(
            select(GenerationUnit.chunk_id)
            .where(GenerationUnit.run_id == run_id, GenerationUnit.state == UnitState.pending)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if rows:
        db.execute(
            update(GenerationUnit)
            .where(GenerationUnit.run_id == run_id, GenerationUnit.chunk_id.in_(rows))
            .values(state=UnitState.queued)
        )
    db.commit()
    return list(rows)


def count_unit(db: Session, run_id: uuid.UUID) -> bool:
    """Record a finished (done or failed) unit. Returns True if this was the last one."""
    done, total = db.execute(
        text(
            "UPDATE generation_runs SET done_chunks = done_chunks + 1, updated_at = now() "
            "WHERE id = :id RETURNING done_chunks, total_chunks"
        ),
        {"id": run_id},
    ).one()
    claimed = None
    if done >= total:
        claimed = db.execute(
            update(GenerationRun)
            .where(GenerationRun.id == run_id, GenerationRun.state == GenState.running)
            .values(state=GenState.finalizing)
            .returning(GenerationRun.id)
        ).first()
    db.commit()
    return claimed is not None


def pause_for_quota(db: Session, run: GenerationRun, retry_after: float) -> datetime:
    resume_at = datetime.now(UTC) + timedelta(seconds=retry_after + 5)
    db.execute(
        update(GenerationRun)
        .where(GenerationRun.id == run.id, GenerationRun.state == GenState.running)
        .values(state=GenState.waiting_quota, resume_at=resume_at)
    )
    db.commit()
    return resume_at


# ---------------- finalize ----------------


@dataclass
class FinalizeResult:
    kept: int
    train: int
    eval: int
    dropped: dict[str, int]


def eval_size(kept: int) -> int:
    if kept == 0:
        return 0
    minimum = 5 if kept >= 50 else 1
    return max(minimum, round(kept * 0.1))


def finalize_pairs(db: Session, run: GenerationRun, project: Project) -> FinalizeResult:
    # every generated pair still in the project: a new dataset discards older runs' pairs first, so anything
    # left from an earlier run belongs to this dataset ("generate more" adds to it)
    full_runs = select(GenerationRun.id).where(
        GenerationRun.project_id == run.project_id, GenerationRun.kind == GenKind.full
    )
    pairs = list(
        db.scalars(
            select(DatasetPair)
            .where(DatasetPair.run_id.in_(full_runs), DatasetPair.kept.is_(True))
            .order_by(DatasetPair.created_at)
        )
    )
    dropped: dict[str, int] = defaultdict(int)

    # 1. exact duplicates (normalized question), then near-duplicates by embedding
    seen_q: dict[str, DatasetPair] = {}
    survivors: list[DatasetPair] = []
    for p in pairs:
        key = formats.dedupe_key(p.dataset_format, p.question, p.record)
        if key in seen_q:
            p.kept, p.dropped_reason, p.duplicate_of = False, "duplicate", seen_q[key].id
            dropped["duplicate"] += 1
            continue
        seen_q[key] = p
        survivors.append(p)
    vectors = (
        get_encoder().passages(
            [formats.embed_text(p.dataset_format, p.question, p.answer, p.record) for p in survivors]
        )
        if survivors
        else []
    )
    unique: list[tuple[DatasetPair, list[float]]] = []
    for p, v in zip(survivors, vectors, strict=True):
        match = next((u for u, uv in unique if cosine(v, uv) > DUPLICATE_COSINE), None)
        if match is not None:
            p.kept, p.dropped_reason, p.duplicate_of = False, "duplicate", match.id
            dropped["duplicate"] += 1
        else:
            unique.append((p, v))

    # 2. trim to target: best scores first, round-robin across chunks for coverage
    by_chunk: dict[uuid.UUID | None, list[DatasetPair]] = defaultdict(list)
    for p, _ in unique:
        by_chunk[p.chunk_id].append(p)
    for group in by_chunk.values():
        group.sort(key=lambda p: -((p.judge_correctness or 0) + (p.judge_style or 0)))
    ordered: list[DatasetPair] = []
    while any(by_chunk.values()):
        for group in by_chunk.values():
            if group:
                ordered.append(group.pop(0))
    keep, surplus = ordered[: run.target_pairs], ordered[run.target_pairs :]
    for p in surplus:
        p.kept, p.dropped_reason = False, "over_target"
        dropped["over_target"] += 1

    # 3. 90/10 split, stratified by document, reproducible per project
    chunk_doc = dict(
        db.execute(
            select(Chunk.id, Chunk.document_id).where(Chunk.id.in_([p.chunk_id for p in keep if p.chunk_id]))
        ).all()
    )
    rng = random.Random(str(project.id))  # noqa: S311
    groups: dict[uuid.UUID | None, list[DatasetPair]] = defaultdict(list)
    for p in keep:
        groups[chunk_doc.get(p.chunk_id) if p.chunk_id else None].append(p)
    want_eval = eval_size(len(keep))
    eval_set: list[DatasetPair] = []
    for group in groups.values():
        rng.shuffle(group)
        take = round(len(group) * want_eval / max(len(keep), 1))
        eval_set.extend(group[:take])
    remaining = [p for p in keep if p not in eval_set]
    rng.shuffle(remaining)
    while len(eval_set) < want_eval and remaining:
        eval_set.append(remaining.pop())
    eval_ids = {p.id for p in eval_set[:want_eval]}
    for p in keep:
        p.split = PairSplit.eval if p.id in eval_ids else PairSplit.train
        p.embedding = None

    for reason, n in db.execute(
        select(DatasetPair.dropped_reason, func.count())
        .where(
            DatasetPair.run_id == run.id,
            DatasetPair.kept.is_(False),
            DatasetPair.dropped_reason.in_(["judge_low", "judge_failed"]),
        )
        .group_by(DatasetPair.dropped_reason)
    ):
        if reason:
            dropped[reason] += n
    return FinalizeResult(kept=len(keep), train=len(keep) - len(eval_ids), eval=len(eval_ids), dropped=dict(dropped))
