import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.errors import Conflict, NotFound
from doctune.models.enums import ProjectStatus
from doctune.models.generation import DatasetPair, DatasetVersion, PairOrigin, PairSplit, StyleConfig
from doctune.models.project import Project
from doctune.routers.deps import DB, LockedProject, OwnedProject, StorageDep
from doctune.schemas.common import Page
from doctune.schemas.generation import (
    ApproveIn,
    BulkIn,
    BulkOut,
    DatasetStats,
    DatasetVersionOut,
    ExportIn,
    ExportOut,
    PairCreate,
    PairOut,
    PairPatch,
)
from doctune.schemas.projects import ProjectOut
from doctune.services import dataset as dataset_service
from doctune.services import formats
from doctune.services import projects as project_service
from doctune.services.transitions import Actor
from doctune.services.views import project_out

router = APIRouter(prefix="/projects/{project_id}", tags=["dataset"])


def _editable(project: Project) -> None:
    if project.status != ProjectStatus.in_review:
        raise Conflict("The dataset can only be edited while it's in review.", code="invalid_state")


async def _pair(db: AsyncSession, project: Project, pair_id: uuid.UUID) -> DatasetPair:
    pair = await db.scalar(dataset_service.dataset_pairs(project.id).where(DatasetPair.id == pair_id))
    if pair is None:
        raise NotFound("Pair not found")
    return pair


@router.get("/pairs")
async def list_pairs(
    project: OwnedProject,
    db: DB,
    split: Literal["train", "eval", "all"] = "all",
    kept: bool | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal["created", "score", "-score"] = "created",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[str | None, Query(pattern=r"^\d+$", description="opaque cursor from `next_cursor`")] = None,
) -> Page[PairOut]:
    offset = int(cursor or 0)
    stmt = dataset_service.dataset_pairs(project.id)
    if split != "all":
        stmt = stmt.where(DatasetPair.split == PairSplit(split))
    if kept is not None:
        stmt = stmt.where(DatasetPair.kept.is_(kept))
    if q:
        like = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(
            or_(DatasetPair.question.ilike(like, escape="\\"), DatasetPair.answer.ilike(like, escape="\\"))
        )
    score = DatasetPair.judge_correctness + DatasetPair.judge_style
    if sort == "score":
        stmt = stmt.order_by(score.asc().nulls_first(), DatasetPair.id)
    elif sort == "-score":
        stmt = stmt.order_by(score.desc().nulls_last(), DatasetPair.id)
    else:
        stmt = stmt.order_by(DatasetPair.created_at, DatasetPair.id)
    rows = list((await db.scalars(stmt.offset(offset).limit(limit + 1))).all())
    return Page(
        items=await dataset_service.pair_out(db, rows[:limit]),
        next_cursor=str(offset + limit) if len(rows) > limit else None,
    )


@router.patch("/pairs/{pair_id}")
async def patch_pair(pair_id: uuid.UUID, body: PairPatch, project: LockedProject, db: DB) -> PairOut:
    _editable(project)
    pair = await _pair(db, project, pair_id)
    changes = body.model_dump(exclude_unset=True)
    if body.record is not None:
        if body.record.format != pair.dataset_format:
            raise Conflict("This pair is in a different dataset format.", code="format_mismatch")
        formats.apply(pair, body.record)
        pair.edited = True
    if "question" in changes or "answer" in changes:
        pair.edited = True
    if "question" in changes:
        pair.question = changes["question"].strip()
    if "answer" in changes:
        pair.answer = changes["answer"].strip()
    if "kept" in changes:
        pair.kept = changes["kept"]
        pair.dropped_reason = None if changes["kept"] else "user_deleted"
    if "split" in changes:
        pair.split = PairSplit(changes["split"])
    project.dataset_version_id = None  # any edit requires approving again
    await db.commit()
    await db.refresh(pair)
    return (await dataset_service.pair_out(db, [pair]))[0]


@router.post("/pairs", status_code=status.HTTP_201_CREATED)
async def create_pair(body: PairCreate, project: LockedProject, db: DB) -> PairOut:
    _editable(project)
    fmt = await dataset_service.dataset_format(db, project)
    record = body.record
    if record is None:
        assert body.question is not None and body.answer is not None  # PairCreate guarantees one or the other
        record = formats.convert(formats.DEFAULT_FORMAT, body.question, body.answer, None, fmt)
        assert record is not None  # a question and an answer fit every format
    if record.format != fmt:
        raise Conflict("This project uses a different dataset format.", code="format_mismatch")
    pair = DatasetPair(project_id=project.id, origin=PairOrigin.user_added, kept=True, split=PairSplit(body.split))
    formats.apply(pair, record)
    db.add(pair)
    project.dataset_version_id = None
    await db.commit()
    await db.refresh(pair)
    return (await dataset_service.pair_out(db, [pair]))[0]


@router.post("/pairs/bulk")
async def bulk_pairs(body: BulkIn, project: LockedProject, db: DB) -> BulkOut:
    _editable(project)
    actions: dict[str, dict[str, object]] = {
        "drop": {"kept": False, "dropped_reason": "user_deleted"},
        "restore": {"kept": True, "dropped_reason": None},
        "move_to_train": {"split": PairSplit.train},
        "move_to_eval": {"split": PairSplit.eval},
    }
    values = actions[body.action]
    result = await db.execute(
        update(DatasetPair)
        .where(DatasetPair.project_id == project.id, DatasetPair.preview.is_(False), DatasetPair.id.in_(body.ids))
        .values(**values)
    )
    project.dataset_version_id = None
    await db.commit()
    return BulkOut(updated=getattr(result, "rowcount", 0) or 0)


@router.get("/dataset/stats")
async def dataset_stats(project: OwnedProject, db: DB) -> DatasetStats:
    return await dataset_service.stats(db, project)


@router.post("/dataset/export")
async def export_dataset(project: OwnedProject, db: DB, storage: StorageDep, body: ExportIn | None = None) -> ExportOut:
    pairs = list(
        (
            await db.scalars(
                dataset_service.dataset_pairs(project.id)
                .where(DatasetPair.kept.is_(True))
                .order_by(DatasetPair.created_at)
            )
        ).all()
    )
    if not pairs:
        raise Conflict("There are no pairs to export yet.", code="empty_dataset")
    style = await db.get(StyleConfig, project.style_id) if project.style_id else None
    system_prompt = style.description if style and style.system_prompt_in_data else None
    key = f"u/{project.user_id}/p/{project.id}/dataset/export-{int(time.time())}.jsonl"
    native = bool(body and body.shape == "native")
    storage.write_bytes(key, dataset_service.jsonl(pairs, system_prompt, native=native))
    url = storage.presign_get(key, filename=f"doctune-dataset-{project.id.hex[:8]}.jsonl")
    return ExportOut(url=url.url, expires_at=url.expires_at)


@router.post("/dataset/approve")
async def approve_dataset(
    project: LockedProject, db: DB, storage: StorageDep, body: ApproveIn | None = None
) -> DatasetVersionOut:
    _editable(project)
    version = await dataset_service.approve(db, storage, project, allow_small=bool(body and body.allow_small))
    return DatasetVersionOut.model_validate(version)


@router.get("/dataset/version")
async def current_version(project: OwnedProject, db: DB) -> DatasetVersionOut | None:
    if project.dataset_version_id is None:
        return None
    row = await db.get(DatasetVersion, project.dataset_version_id)
    return DatasetVersionOut.model_validate(row) if row else None


@router.post("/dataset/restyle")
async def restyle(project: LockedProject, db: DB) -> ProjectOut:
    _editable(project)
    await dataset_service.discard_generated(db, project)
    await project_service.transition(db, project, ProjectStatus.awaiting_style, actor=Actor.user)
    return await project_out(db, project)
