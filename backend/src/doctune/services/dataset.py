"""Dataset review: queries over a project's (non-preview) pairs, stats, approval, estimates."""

import hashlib
import math
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.config import get_settings
from doctune.core.errors import Conflict
from doctune.core.storage import Storage
from doctune.llm.providers import PROVIDERS
from doctune.models.document import Chunk
from doctune.models.generation import (
    DatasetPair,
    DatasetVersion,
    GenerationRun,
    GenerationUnit,
    GenKind,
    GenState,
    KeyStatus,
    PairSplit,
    ProviderKey,
    StyleConfig,
    UnitState,
)
from doctune.models.project import Project
from doctune.parsing.chunker import count_tokens
from doctune.schemas.generation import ChunkRef, DatasetStats, Estimate, MoreInfo, PairOut, ResumeInfo
from doctune.services import formats
from doctune.services.generation import FINISH_EARLY_MIN_PAIRS, Plan, plan_run

MIN_DATASET = 50
MIN_EVAL = 5
# a run finished early can be approved on purpose with as few pairs as finishing early allows
SMALL_DATASET = FINISH_EARLY_MIN_PAIRS


def min_eval(kept: int) -> int:
    """Matches the split finalize makes: 10% held out, at least 5 once the dataset is full-size, else at least 1."""
    return MIN_EVAL if kept >= MIN_DATASET else 1


async def more_plan(db: AsyncSession, project: Project, kept: int) -> tuple[Plan, MoreInfo] | None:
    """Plan a "generate more" pass toward the project's target, or None when the target is already met."""
    if kept >= project.target_pairs:
        return None
    chunk_ids = list(
        (
            await db.scalars(
                select(Chunk.id).where(Chunk.project_id == project.id).order_by(Chunk.document_id, Chunk.ordinal)
            )
        ).all()
    )
    fmt = await dataset_format(db, project)
    plan = plan_run(chunk_ids, project.target_pairs - kept, f"{project.id}:{kept}", formats.max_per_chunk(fmt))
    if not plan.chunk_ids:
        return None
    info = MoreInfo(
        target_pairs=project.target_pairs, sections=len(plan.chunk_ids), pairs_to_generate=plan.supported_pairs
    )
    return plan, info


async def dataset_format(db: AsyncSession, project: Project) -> str:
    style_format = (
        await db.scalar(select(StyleConfig.dataset_format).where(StyleConfig.id == project.style_id))
        if project.style_id
        else None
    )
    return style_format or formats.DEFAULT_FORMAT


async def resumable_run(db: AsyncSession, project: Project) -> ResumeInfo | None:
    """The latest full run, if it was finished early with the current style and still has sections to generate."""
    run = await db.scalar(
        select(GenerationRun)
        .where(GenerationRun.project_id == project.id, GenerationRun.kind == GenKind.full)
        .order_by(GenerationRun.created_at.desc())
        .limit(1)
    )
    if run is None or run.state != GenState.done or run.style_id != project.style_id:
        return None
    remaining = await db.scalar(
        select(func.count())
        .select_from(GenerationUnit)
        .where(GenerationUnit.run_id == run.id, GenerationUnit.state == UnitState.cancelled)
    )
    if not remaining:
        return None
    return ResumeInfo(run_id=run.id, remaining_chunks=remaining, total_chunks=run.total_chunks)


def dataset_pairs(project_id: uuid.UUID) -> Select[DatasetPair]:
    return select(DatasetPair).where(DatasetPair.project_id == project_id, DatasetPair.preview.is_(False))


async def pair_out(db: AsyncSession, pairs: list[DatasetPair]) -> list[PairOut]:
    chunk_ids = {p.chunk_id for p in pairs if p.chunk_id}
    chunks = {}
    if chunk_ids:
        rows = await db.execute(select(Chunk.id, Chunk.section_path, Chunk.text).where(Chunk.id.in_(chunk_ids)))
        chunks = {cid: ChunkRef(id=cid, section_path=path, excerpt=text[:400]) for cid, path, text in rows}
    return [
        PairOut(
            id=p.id,
            dataset_format=p.dataset_format,
            question=p.question,
            answer=p.answer,
            record=formats.view(p.dataset_format, p.question, p.answer, p.record),
            split=p.split,
            origin=p.origin,
            judge_correctness=p.judge_correctness,
            judge_style=p.judge_style,
            judge_reason=p.judge_reason,
            kept=p.kept,
            dropped_reason=p.dropped_reason,
            edited=p.edited,
            chunk=chunks.get(p.chunk_id) if p.chunk_id else None,
        )
        for p in pairs
    ]


async def counts(db: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(DatasetPair.split, func.count())
        .where(DatasetPair.project_id == project_id, DatasetPair.preview.is_(False), DatasetPair.kept.is_(True))
        .group_by(DatasetPair.split)
    )
    by_split = dict(rows.all())
    train = by_split.get(PairSplit.train, 0) + by_split.get(PairSplit.unassigned, 0)
    evals = by_split.get(PairSplit.eval, 0)
    return {"pairs_kept": train + evals, "pairs_train": train, "pairs_eval": evals}


async def stats(db: AsyncSession, project: Project) -> DatasetStats:
    project_id = project.id
    pairs = list((await db.scalars(dataset_pairs(project_id))).all())
    kept = [p for p in pairs if p.kept]
    c = await counts(db, project_id)
    dropped = Counter(p.dropped_reason or "dropped" for p in pairs if p.kept is False)
    scored = [p for p in kept if p.judge_correctness is not None]
    buckets = Counter()  # type: Counter[str]
    for p in kept:
        words = len(p.answer.split())
        buckets["<25" if words < 25 else "25-75" if words < 75 else "75-200" if words < 200 else "200+"] += 1
    return DatasetStats(
        kept=c["pairs_kept"],
        train=c["pairs_train"],
        eval=c["pairs_eval"],
        dropped_by_reason=dict(dropped),
        avg_correctness=round(sum(p.judge_correctness or 0 for p in scored) / len(scored), 2) if scored else None,
        avg_style=round(sum(p.judge_style or 0 for p in scored) / len(scored), 2) if scored else None,
        answer_words=dict(buckets),
        min_pairs=MIN_DATASET,
        small_min_pairs=SMALL_DATASET,
        max_pairs=get_settings().max_pairs,
        min_eval=min_eval(c["pairs_kept"]),
        resume=(resume := await resumable_run(db, project)),
        # completing a stopped run comes first; offering both would double up on the same sections
        more=None if resume else (m[1] if (m := await more_plan(db, project, c["pairs_kept"])) else None),
    )


def jsonl(pairs: list[DatasetPair], system_prompt: str | None, *, native: bool = False) -> bytes:
    line = formats.native_line if native else formats.training_line
    return (
        "\n".join(line(p.dataset_format, p.question, p.answer, p.record, system_prompt) for p in pairs) + "\n"
    ).encode()


async def approve(db: AsyncSession, storage: Storage, project: Project, *, allow_small: bool = False) -> DatasetVersion:
    kept = list(
        (
            await db.scalars(
                dataset_pairs(project.id).where(DatasetPair.kept.is_(True)).order_by(DatasetPair.created_at)
            )
        ).all()
    )
    max_pairs = get_settings().max_pairs
    fmt = await dataset_format(db, project)
    if any(p.dataset_format != fmt for p in kept):
        raise Conflict(
            "Some kept pairs are in a different dataset format than this project. Remove them before approving.",
            code="format_mismatch",
        )
    for p in kept:
        if p.split == PairSplit.unassigned:
            p.split = PairSplit.train
    train = [p for p in kept if p.split == PairSplit.train]
    evals = [p for p in kept if p.split == PairSplit.eval]
    if len(kept) < (SMALL_DATASET if allow_small else MIN_DATASET):
        raise Conflict(
            f"Keep at least {SMALL_DATASET if allow_small else MIN_DATASET} pairs before approving "
            f"(you have {len(kept)}).",
            code="dataset_too_small",
        )
    if len(kept) > max_pairs:
        raise Conflict(
            f"The dataset can have at most {max_pairs} pairs (you have {len(kept)}).", code="dataset_too_large"
        )
    if len(evals) < min_eval(len(kept)):
        raise Conflict(f"Move at least {min_eval(len(kept))} pairs to the evaluation set.", code="eval_too_small")

    style = await db.get(StyleConfig, project.style_id) if project.style_id else None
    system_prompt = style.description if style and style.system_prompt_in_data else None
    version = (
        await db.scalar(
            select(func.coalesce(func.max(DatasetVersion.version), 0)).where(DatasetVersion.project_id == project.id)
        )
        or 0
    ) + 1
    base = f"u/{project.user_id}/p/{project.id}/dataset/v{version}"
    train_data, eval_data = jsonl(train, system_prompt), jsonl(evals, system_prompt)
    storage.write_bytes(f"{base}/train.jsonl", train_data)
    storage.write_bytes(f"{base}/eval.jsonl", eval_data)
    row = DatasetVersion(
        project_id=project.id,
        version=version,
        train_count=len(train),
        eval_count=len(evals),
        train_key=f"{base}/train.jsonl",
        eval_key=f"{base}/eval.jsonl",
        sha256_train=hashlib.sha256(train_data).hexdigest(),
        sha256_eval=hashlib.sha256(eval_data).hexdigest(),
        system_prompt=system_prompt,
        dataset_format=fmt,
        stats={"approved_at": datetime.now(UTC).isoformat()},
    )
    db.add(row)
    await db.flush()
    project.dataset_version_id = row.id
    await db.commit()
    await db.refresh(row)
    return row


async def discard_generated(db: AsyncSession, project: Project) -> None:
    """Restyle: drop the generated dataset (previews stay for reference; user-added pairs too)."""
    full_runs = select(GenerationRun.id).where(
        GenerationRun.project_id == project.id, GenerationRun.kind == GenKind.full
    )
    await db.execute(delete(DatasetPair).where(DatasetPair.run_id.in_(full_runs)))
    project.dataset_version_id = None


async def estimate(db: AsyncSession, project: Project, style: StyleConfig | None) -> Estimate:
    chunk_rows = (await db.execute(select(Chunk.id, Chunk.token_count).where(Chunk.project_id == project.id))).all()
    fmt = style.dataset_format if style else formats.DEFAULT_FORMAT
    plan = plan_run([cid for cid, _ in chunk_rows], project.target_pairs, str(project.id), formats.max_per_chunk(fmt))
    tokens_by_chunk = dict(chunk_rows)
    style_tokens = count_tokens(style.description + " ".join(e["output"] for e in style.examples)) if style else 300
    per_pair = 250 * formats.relative_cost(fmt)
    gen_tokens = sum(
        int(tokens_by_chunk[c] + style_tokens + 350 + plan.pairs_per_chunk * per_pair) for c in plan.chunk_ids
    )
    judge_tokens = int(gen_tokens * 0.6)
    total = gen_tokens + judge_tokens
    requests = len(plan.chunk_ids) * 2

    keys = (
        await db.scalars(
            select(ProviderKey).where(ProviderKey.user_id == project.user_id, ProviderKey.status != KeyStatus.invalid)
        )
    ).all()
    models = [m for k in keys if k.provider in PROVIDERS for m in PROVIDERS[k.provider].models]
    tpm = sum(m.tpm for m in models) or 1
    rpm = sum(m.rpm for m in models) or 1
    tpd = sum(m.tpd or 10_000_000 for m in models) or 1
    minutes = max(total / tpm, requests / rpm)
    days = total / tpd
    return Estimate(
        chunks=len(plan.chunk_ids),
        pairs_per_chunk=plan.pairs_per_chunk,
        supported_pairs=plan.supported_pairs,
        target_pairs=project.target_pairs,
        est_requests=requests,
        est_tokens=total,
        est_minutes=round(minutes, 1),
        est_days=round(days, 2),
        providers=sorted({k.provider.value for k in keys}),
        fits_daily_quota=bool(models) and days <= 1,
    )


def plan_for(chunk_ids: list[uuid.UUID], target: int, project_id: uuid.UUID) -> tuple[list[uuid.UUID], int]:
    plan = plan_run(chunk_ids, target, str(project_id))
    return plan.chunk_ids, plan.pairs_per_chunk


def preview_chunks(chunk_rows: list[tuple[uuid.UUID, uuid.UUID, int]], n: int, seed: str) -> list[uuid.UUID]:
    """Pick up to n chunks spread across documents, skipping tiny ones."""
    import random

    usable = [r for r in chunk_rows if r[2] >= 100] or chunk_rows
    by_doc: dict[uuid.UUID, list[uuid.UUID]] = {}
    for cid, doc, _ in usable:
        by_doc.setdefault(doc, []).append(cid)
    rng = random.Random(seed)  # noqa: S311
    for ids in by_doc.values():
        rng.shuffle(ids)
    picked: list[uuid.UUID] = []
    while len(picked) < n and any(by_doc.values()):
        for ids in by_doc.values():
            if ids and len(picked) < n:
                picked.append(ids.pop())
    return picked


def ceil_div(a: int, b: int) -> int:
    return math.ceil(a / b)
