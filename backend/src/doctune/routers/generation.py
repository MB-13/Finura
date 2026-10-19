import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.auth import CurrentUserDep
from doctune.core.errors import Conflict, NotFound
from doctune.core.ratelimit import limit
from doctune.llm.prompts import GEN_VERSIONS
from doctune.models.document import Chunk
from doctune.models.enums import ProjectStatus
from doctune.models.generation import (
    DatasetPair,
    GenerationRun,
    GenerationUnit,
    GenKind,
    GenState,
    KeyStatus,
    ProviderKey,
    StyleConfig,
    UnitState,
)
from doctune.models.project import Project
from doctune.routers.deps import DB, LockedProject, OwnedProject
from doctune.schemas.generation import Estimate, GenerateIn, PairOut, PreviewIn, RunOut, StyleOut
from doctune.schemas.projects import ProjectOut
from doctune.services import dataset as dataset_service
from doctune.services import formats
from doctune.services import projects as project_service
from doctune.services import style as style_service
from doctune.services.formats import FormatInfo
from doctune.services.generation import FINISH_EARLY_MIN_PAIRS, plan_run
from doctune.services.style import TEMPLATES, StyleIn, StyleTemplate
from doctune.services.transitions import Actor
from doctune.services.views import _style_out, project_out

router = APIRouter(tags=["generation"])


def style_out(row: StyleConfig) -> StyleOut:
    return _style_out(row)


async def _run(db: AsyncSession, project_id: uuid.UUID, run_id: uuid.UUID) -> GenerationRun:
    run = await db.get(GenerationRun, run_id)
    if run is None or run.project_id != project_id:
        raise NotFound("Run not found")
    return run


async def _has_usable_key(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(ProviderKey.id)
            .where(ProviderKey.user_id == user_id, ProviderKey.status != KeyStatus.invalid)
            .limit(1)
        )
    ) is not None


async def _ensure_not_busy(db: AsyncSession, user_id: uuid.UUID) -> None:
    busy = await db.scalar(
        select(GenerationRun.id)
        .where(
            GenerationRun.user_id == user_id,
            GenerationRun.kind == GenKind.full,
            GenerationRun.state.in_([GenState.queued, GenState.running, GenState.waiting_quota, GenState.finalizing]),
        )
        .limit(1)
    )
    if busy is not None:
        raise Conflict(
            "Another project of yours is generating. One generation at a time keeps you within free limits.",
            code="generation_busy",
        )


@router.get("/style-templates")
async def list_templates(_: CurrentUserDep) -> list[StyleTemplate]:
    return TEMPLATES


@router.get("/dataset-formats")
async def list_dataset_formats(_: CurrentUserDep) -> list[FormatInfo]:
    return list(formats.FORMATS.values())


async def _prompt_version(db: AsyncSession, project: Project) -> str:
    return GEN_VERSIONS[await dataset_service.dataset_format(db, project)]


@router.get("/projects/{project_id}/style")
async def get_style(project: OwnedProject, db: DB) -> StyleOut | None:
    if project.style_id is None:
        return None
    row = await db.get(StyleConfig, project.style_id)
    return style_out(row) if row else None


@router.put("/projects/{project_id}/style")
async def put_style(body: StyleIn, project: LockedProject, db: DB) -> StyleOut:
    if project.status != ProjectStatus.awaiting_style:
        raise Conflict(
            "The style can be changed once documents are processed and before generation.", code="invalid_state"
        )
    row = await style_service.save(db, project, body)
    return style_out(row)


@router.post(
    "/projects/{project_id}/preview",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit("preview", 10))],
)
async def start_preview(body: PreviewIn, project: LockedProject, db: DB) -> RunOut:
    from doctune.workers.tasks.generate import generate_preview

    if project.style_id is None:
        raise Conflict("Describe the style first.", code="style_required")
    if not await _has_usable_key(db, project.user_id):
        raise Conflict("Connect an API key in Settings first.", code="key_required")
    rows = (
        await db.execute(select(Chunk.id, Chunk.document_id, Chunk.token_count).where(Chunk.project_id == project.id))
    ).all()
    chunk_ids = dataset_service.preview_chunks(
        list(rows), body.n_chunks, f"{project.id}:{datetime.now(UTC).isoformat()}"
    )
    if not chunk_ids:
        raise Conflict("No document text to preview.", code="no_chunks")
    run = GenerationRun(
        project_id=project.id,
        user_id=project.user_id,
        style_id=project.style_id,
        kind=GenKind.preview,
        state=GenState.queued,
        prompt_version=await _prompt_version(db, project),
        pairs_per_chunk=body.pairs_per_chunk,
        target_pairs=len(chunk_ids) * body.pairs_per_chunk,
        total_chunks=len(chunk_ids),
    )
    db.add(run)
    await db.flush()
    db.add_all(GenerationUnit(run_id=run.id, chunk_id=cid) for cid in chunk_ids)
    await project_service.transition(db, project, ProjectStatus.previewing, actor=Actor.user)
    generate_preview.delay(str(run.id))
    await db.refresh(run)
    return RunOut.model_validate(run)


@router.get("/projects/{project_id}/runs/{run_id}")
async def get_run(run_id: uuid.UUID, project: OwnedProject, db: DB) -> RunOut:
    return RunOut.model_validate(await _run(db, project.id, run_id))


@router.get("/projects/{project_id}/runs/{run_id}/pairs")
async def run_pairs(run_id: uuid.UUID, project: OwnedProject, db: DB) -> list[PairOut]:
    run = await _run(db, project.id, run_id)
    pairs = (
        await db.scalars(
            select(DatasetPair).where(DatasetPair.run_id == run.id).order_by(DatasetPair.created_at).limit(200)
        )
    ).all()
    return await dataset_service.pair_out(db, list(pairs))


@router.get("/projects/{project_id}/estimate")
async def get_estimate(project: OwnedProject, db: DB) -> Estimate:
    style = await db.get(StyleConfig, project.style_id) if project.style_id else None
    return await dataset_service.estimate(db, project, style)


@router.post("/projects/{project_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(body: GenerateIn, project: LockedProject, db: DB) -> RunOut:
    from doctune.workers.tasks.generate import start_full_run

    if project.style_id is None:
        raise Conflict("Describe the style first.", code="style_required")
    preview_ok = await db.scalar(
        select(GenerationRun.id)
        .where(
            GenerationRun.project_id == project.id,
            GenerationRun.kind == GenKind.preview,
            GenerationRun.state == GenState.done,
            GenerationRun.style_id == project.style_id,
        )
        .limit(1)
    )
    if preview_ok is None:
        raise Conflict("Generate a preview with the current style first.", code="preview_required")
    if not await _has_usable_key(db, project.user_id):
        raise Conflict("Connect an API key in Settings first.", code="key_required")
    await _ensure_not_busy(db, project.user_id)

    chunk_ids = list(
        (
            await db.scalars(
                select(Chunk.id).where(Chunk.project_id == project.id).order_by(Chunk.document_id, Chunk.ordinal)
            )
        ).all()
    )
    fmt = await dataset_service.dataset_format(db, project)
    plan = plan_run(chunk_ids, project.target_pairs, str(project.id), formats.max_per_chunk(fmt))
    await dataset_service.discard_generated(db, project)
    run = GenerationRun(
        project_id=project.id,
        user_id=project.user_id,
        style_id=project.style_id,
        kind=GenKind.full,
        state=GenState.queued,
        prompt_version=await _prompt_version(db, project),
        pairs_per_chunk=plan.pairs_per_chunk,
        target_pairs=project.target_pairs,
        total_chunks=len(plan.chunk_ids),
    )
    db.add(run)
    await db.flush()
    db.add_all(GenerationUnit(run_id=run.id, chunk_id=cid) for cid in plan.chunk_ids)
    await project_service.transition(db, project, ProjectStatus.generating, actor=Actor.user)
    start_full_run.delay(str(run.id))
    await db.refresh(run)
    return RunOut.model_validate(run)


@router.post("/projects/{project_id}/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, project: LockedProject, db: DB) -> ProjectOut:
    run = await _run(db, project.id, run_id)
    if run.kind != GenKind.full or run.state not in (GenState.queued, GenState.running, GenState.waiting_quota):
        raise Conflict("This run can't be cancelled now.", code="invalid_state")
    run.state, run.finished_at = GenState.cancelled, datetime.now(UTC)
    await db.execute(
        update(GenerationUnit)
        .where(GenerationUnit.run_id == run.id, GenerationUnit.state.in_([UnitState.pending, UnitState.queued]))
        .values(state=UnitState.cancelled)
    )
    await dataset_service.discard_generated(db, project)
    await project_service.transition(db, project, ProjectStatus.awaiting_style, actor=Actor.user)
    return await project_out(db, project)


@router.post("/projects/{project_id}/runs/{run_id}/finish")
async def finish_run_early(run_id: uuid.UUID, project: LockedProject, db: DB) -> ProjectOut:
    """Stop a full run and build the dataset from the pairs judged so far (e.g. while waiting for quota)."""
    from doctune.workers.tasks.finalize import finalize_run

    run = await db.get(GenerationRun, run_id, with_for_update=True)
    if run is None or run.project_id != project.id:
        raise NotFound("Run not found")
    if run.kind != GenKind.full or run.state not in (GenState.running, GenState.waiting_quota):
        raise Conflict("This run can't be finished now.", code="invalid_state")
    # a "generate more" run adds to earlier pairs, so count the whole dataset
    kept = (await dataset_service.counts(db, project.id))["pairs_kept"]
    if (kept or 0) < FINISH_EARLY_MIN_PAIRS:
        raise Conflict(
            f"Only {kept or 0} pairs have passed the quality check so far; at least {FINISH_EARLY_MIN_PAIRS} are "
            "needed. Let generation continue a little longer.",
            code="too_few_pairs",
        )
    # units still in flight see the run is no longer running and throw their work away
    run.state, run.resume_at = GenState.finalizing, None
    await db.execute(
        update(GenerationUnit)
        .where(GenerationUnit.run_id == run.id, GenerationUnit.state.in_([UnitState.pending, UnitState.queued]))
        .values(state=UnitState.cancelled)
    )
    await db.commit()
    finalize_run.delay(str(run.id))
    await db.refresh(project)
    return await project_out(db, project)


@router.post("/projects/{project_id}/runs/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: uuid.UUID, project: LockedProject, db: DB) -> ProjectOut:
    """Complete a run that was finished early: generate the skipped sections, keeping the pairs and edits so far."""
    from doctune.workers.tasks.generate import start_full_run

    if project.status != ProjectStatus.in_review:
        raise Conflict("Generation can only be completed while the dataset is in review.", code="invalid_state")
    resume = await dataset_service.resumable_run(db, project)
    if resume is None or resume.run_id != run_id:
        raise Conflict("This run has nothing left to generate.", code="invalid_state")
    if not await _has_usable_key(db, project.user_id):
        raise Conflict("Connect an API key in Settings first.", code="key_required")
    await _ensure_not_busy(db, project.user_id)
    run = await _run(db, project.id, run_id)
    run.state, run.finished_at, run.resume_at, run.error = GenState.queued, None, None, None
    await db.execute(
        update(GenerationUnit)
        .where(GenerationUnit.run_id == run.id, GenerationUnit.state == UnitState.cancelled)
        .values(state=UnitState.pending, attempts=0, error=None)
    )
    # the dataset will change, so an earlier approval no longer describes it
    project.dataset_version_id = None
    await project_service.transition(db, project, ProjectStatus.generating, actor=Actor.user)
    start_full_run.delay(str(run.id))
    return await project_out(db, project)


@router.post("/projects/{project_id}/generate/more", status_code=status.HTTP_202_ACCEPTED)
async def generate_more(project: LockedProject, db: DB) -> ProjectOut:
    """Another pass over the documents toward the target, added to the current pairs (which, and edits, are kept)."""
    from doctune.workers.tasks.generate import start_full_run

    if project.status != ProjectStatus.in_review:
        raise Conflict("More pairs can only be generated while the dataset is in review.", code="invalid_state")
    if project.style_id is None:
        raise Conflict("Describe the style first.", code="style_required")
    kept = (await dataset_service.counts(db, project.id))["pairs_kept"]
    planned = await dataset_service.more_plan(db, project, kept)
    if planned is None:
        raise Conflict("Your dataset already reaches its target size.", code="target_reached")
    if not await _has_usable_key(db, project.user_id):
        raise Conflict("Connect an API key in Settings first.", code="key_required")
    await _ensure_not_busy(db, project.user_id)
    plan, _ = planned
    run = GenerationRun(
        project_id=project.id,
        user_id=project.user_id,
        style_id=project.style_id,
        kind=GenKind.full,
        state=GenState.queued,
        prompt_version=await _prompt_version(db, project),
        pairs_per_chunk=plan.pairs_per_chunk,
        target_pairs=project.target_pairs,
        total_chunks=len(plan.chunk_ids),
    )
    db.add(run)
    await db.flush()
    db.add_all(GenerationUnit(run_id=run.id, chunk_id=cid) for cid in plan.chunk_ids)
    # the dataset will change, so an earlier approval no longer describes it
    project.dataset_version_id = None
    await project_service.transition(db, project, ProjectStatus.generating, actor=Actor.user)
    start_full_run.delay(str(run.id))
    return await project_out(db, project)
