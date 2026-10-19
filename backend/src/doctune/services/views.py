"""Build API views of projects (kept separate so later phases can enrich ProjectOut in one place)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.models.enums import ProjectStatus
from doctune.models.generation import DatasetVersion, GenerationRun, GenKind, StyleConfig
from doctune.models.project import Project
from doctune.models.training import Checkpoint, Evaluation, JobToken, TrainingJob
from doctune.schemas.generation import DatasetVersionOut, RunOut, StyleOut
from doctune.schemas.projects import ProjectCounts, ProjectOut
from doctune.schemas.training import EvaluationOut, TrainingJobOut
from doctune.services import dataset as dataset_service
from doctune.services import projects as project_service
from doctune.services import style as style_service
from doctune.services.transitions import allowed_actions
from doctune.training import catalog
from doctune.training.colab import avg_example_tokens, job_minutes


async def project_out(db: AsyncSession, project: Project) -> ProjectOut:
    # reload server-generated columns (updated_at) and any changes made by inline workers
    await db.refresh(project)
    counts = await project_service.counts(db, project.id)
    counts.update(await dataset_service.counts(db, project.id))
    style = await db.get(StyleConfig, project.style_id) if project.style_id else None
    latest_preview = await db.scalar(
        select(GenerationRun)
        .where(GenerationRun.project_id == project.id, GenerationRun.kind == GenKind.preview)
        .order_by(GenerationRun.created_at.desc())
        .limit(1)
    )
    active_run = await db.scalar(
        select(GenerationRun)
        .where(GenerationRun.project_id == project.id, GenerationRun.kind == GenKind.full)
        .order_by(GenerationRun.created_at.desc())
        .limit(1)
    )
    version = await db.get(DatasetVersion, project.dataset_version_id) if project.dataset_version_id else None
    job = await db.scalar(
        select(TrainingJob).where(TrainingJob.project_id == project.id).order_by(TrainingJob.created_at.desc()).limit(1)
    )
    evaluation = await db.scalar(select(Evaluation).where(Evaluation.job_id == job.id)) if job else None
    actions = allowed_actions(project.status, retry_available=project.status_retry_to is not None)
    if project.status in (ProjectStatus.uploaded,) and counts["documents"] == 0:
        actions = [a for a in actions if a != "process"]
    return ProjectOut(
        id=project.id,
        name=project.name,
        status=project.status,
        status_reason=project.status_reason,
        status_message=project.status_message,
        status_changed_at=project.status_changed_at,
        base_model_id=project.base_model_id,
        base_model_license=project.base_model_license,
        gen_provider=project.gen_provider,
        gen_model=project.gen_model,
        target_pairs=project.target_pairs,
        total_bytes=project.total_bytes,
        created_at=project.created_at,
        updated_at=project.updated_at,
        counts=ProjectCounts(**counts),
        allowed_actions=actions,
        style=_style_out(style) if style else None,
        latest_preview=RunOut.model_validate(latest_preview) if latest_preview else None,
        active_run=RunOut.model_validate(active_run) if active_run else None,
        dataset_version=DatasetVersionOut.model_validate(version) if version else None,
        active_job=await job_out(db, job) if job else None,
        evaluation=EvaluationOut.model_validate(evaluation) if evaluation else None,
    )


def _style_out(row: StyleConfig) -> StyleOut:
    style_in = style_service.to_in(row)
    return StyleOut(
        **style_in.model_dump(), id=row.id, created_at=row.created_at, warnings=style_service.warnings_for(style_in)
    )


async def job_out(db: AsyncSession, job: TrainingJob) -> TrainingJobOut:
    out = TrainingJobOut.model_validate(job)
    token = await db.scalar(
        select(JobToken)
        .where(JobToken.job_id == job.id, JobToken.revoked_at.is_(None))
        .order_by(JobToken.created_at.desc())
    )
    ckpt = await db.get(Checkpoint, job.id)
    model = catalog.BY_ID.get(job.base_model_id)
    return out.model_copy(
        update={
            "token_prefix": token.token_prefix if token else None,
            "token_expires_at": token.expires_at if token else None,
            "checkpoint_step": ckpt.step if ckpt else None,
            "checkpoint_uploaded_at": ckpt.uploaded_at if ckpt else None,
            "est_minutes": job_minutes(model, job.max_steps, await avg_example_tokens(db, job.project_id))
            if model
            else None,
        }
    )
