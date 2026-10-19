import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from doctune.core import jobauth
from doctune.core.auth import CurrentUserDep
from doctune.core.config import get_settings
from doctune.core.errors import Conflict, NotFound
from doctune.core.ratelimit import limit
from doctune.models.compute import ComputeStatus
from doctune.models.enums import ProjectStatus
from doctune.models.generation import DatasetVersion
from doctune.models.training import Artifact, Checkpoint, Evaluation, JobState, TrainingJob, TrainingMetric
from doctune.routers.deps import DB, LockedProject, OwnedProject, StorageDep
from doctune.schemas.projects import ProjectOut
from doctune.schemas.training import (
    ArtifactOut,
    BaseModelOut,
    DownloadOut,
    EvaluationOut,
    MetricOut,
    ModelCheckIn,
    PresetOut,
    TokenOut,
    TrainingCreate,
    TrainingCreated,
    TrainingJobOut,
    TrainingSwitch,
)
from doctune.services import compute as compute_service
from doctune.services import projects as project_service
from doctune.services.transitions import Actor
from doctune.services.views import job_out, project_out
from doctune.training import catalog, hf_check
from doctune.training.catalog import BaseModel as CatalogModel
from doctune.training.colab import avg_example_tokens, job_minutes
from doctune.training.hf_check import ModelCheck
from doctune.training.jobs import cancel_job
from doctune.training.presets import PRESETS, Hyperparams, max_steps, resolve
from doctune.training.registry import get_backend

router = APIRouter(tags=["training"])

ACTIVE_JOB_STATES = (JobState.created, JobState.running, JobState.paused, JobState.evaluating)


async def _job(db: AsyncSession, project_id: uuid.UUID, job_id: uuid.UUID) -> TrainingJob:
    job = await db.get(TrainingJob, job_id)
    if job is None or job.project_id != project_id:
        raise NotFound("Training job not found")
    return job


@router.get("/models/catalog")
async def model_catalog(_: CurrentUserDep, db: DB, project_id: uuid.UUID | None = None) -> list[BaseModelOut]:
    train_pairs, avg_tokens = 450, 200.0
    if project_id is not None:
        version = await db.scalar(
            select(DatasetVersion)
            .where(DatasetVersion.project_id == project_id)
            .order_by(DatasetVersion.version.desc())
        )
        if version is not None:
            train_pairs = version.train_count
            avg_tokens = await avg_example_tokens(db, project_id)
    out = []
    chat_limit = get_settings().playground_max_params_b
    for m in catalog.CATALOG:
        est = {}
        for key in PRESETS:
            hp = resolve(key, None, m.params_b)
            est[key] = job_minutes(m, max_steps(train_pairs, hp), avg_tokens)
        out.append(
            BaseModelOut(
                id=m.id,
                display_name=m.display_name,
                params_b=m.params_b,
                license=m.license,
                train_mode=m.train_mode,
                fits_t4=m.fits_t4,
                vram_gb=m.vram_gb,
                recommended=m.recommended,
                playground_supported=m.playground_gguf is not None and m.params_b <= chat_limit,
                note=m.note,
                est_minutes=est,
            )
        )
    return out


@router.post("/models/check", dependencies=[Depends(limit("model_check", 20))])
async def check_model(body: ModelCheckIn, _: CurrentUserDep) -> ModelCheck:
    return await run_in_threadpool(hf_check.check, body.hf_id.strip())


@router.get("/training/presets")
async def presets(_: CurrentUserDep) -> list[PresetOut]:
    return [PresetOut(**p.model_dump()) for p in PRESETS.values()]


@router.post("/projects/{project_id}/training", status_code=status.HTTP_201_CREATED)
async def create_training(
    body: TrainingCreate, project: LockedProject, db: DB, user: CurrentUserDep
) -> TrainingCreated:
    if project.status != ProjectStatus.in_review:
        raise Conflict("Approve your dataset before starting training.", code="invalid_state")
    if project.dataset_version_id is None:
        raise Conflict("Approve your dataset before starting training.", code="dataset_not_approved")
    if body.backend == "kaggle":
        account = await compute_service.get_kaggle(db, user.id)
        if account is None or account.status != ComputeStatus.ok:
            raise Conflict(
                "Connect a working Kaggle account in Settings first, or start training with Colab.",
                code="kaggle_not_connected",
            )

    model = catalog.BY_ID.get(body.base_model_id)
    is_llama = False
    if model is None:
        check = await run_in_threadpool(hf_check.check, body.base_model_id.strip())
        if body.backend == "kaggle" and check.gated:
            raise Conflict(
                "This model is gated and needs your Hugging Face token, which only the Colab notebook can use.",
                code="kaggle_gated_model",
            )
        if not check.ok:
            raise Conflict(
                f"This model can't be used: {', '.join(check.blocking)}.",
                code="model_blocked",
                details={"check": check.model_dump()},
            )
        if not check.license_ok and not body.license_ack:
            raise Conflict("Please review and accept this model's license.", code="license_ack_required")
        model = CatalogModel(
            id=check.hf_id,
            display_name=check.hf_id,
            params_b=check.params_b or 8.0,
            license=check.license or "unknown",
            train_mode=check.train_mode,
            fits_t4="unconfirmed",
            vram_gb=0,
            sec_per_step=5.0,
            startup_min=3.0,
        )
        is_llama = check.is_llama
        project.base_model_is_custom = True
    else:
        project.base_model_is_custom = False
    hp = resolve(body.preset, body.advanced, model.params_b)

    project.base_model_id = model.id
    project.base_model_license = model.license
    if body.license_ack:
        project.license_ack_at = datetime.now(UTC)
    result = await get_backend(body.backend).submit_job(db, project, model, body.preset, hp, is_llama=is_llama)
    await project_service.transition(db, project, ProjectStatus.awaiting_run, actor=Actor.user)
    if result.after_commit is not None:
        result.after_commit()
    return TrainingCreated(job=await job_out(db, result.job), token=result.token, notebook_url=result.launch_url)


@router.post("/projects/{project_id}/training/{job_id}/switch")
async def switch_training_backend(
    job_id: uuid.UUID, body: TrainingSwitch, project: LockedProject, db: DB, user: CurrentUserDep
) -> TrainingCreated:
    """Move a Colab job nobody has connected to yet onto Kaggle, keeping the model and settings."""
    job = await _job(db, project.id, job_id)
    if job.backend == body.backend:
        raise Conflict("This job already runs there.", code="invalid_state")
    if job.state != JobState.created or project.status != ProjectStatus.awaiting_run:
        raise Conflict("Training has already started in the notebook; cancel it first.", code="invalid_state")
    account = await compute_service.get_kaggle(db, user.id)
    if account is None or account.status != ComputeStatus.ok:
        raise Conflict("Connect a working Kaggle account in Settings first.", code="kaggle_not_connected")
    model = catalog.BY_ID.get(job.base_model_id)
    if model is None:
        check = await run_in_threadpool(hf_check.check, job.base_model_id)
        if check.gated:
            raise Conflict(
                "This model is gated and needs your Hugging Face token, which only the Colab notebook can use.",
                code="kaggle_gated_model",
            )
        model = CatalogModel(
            id=job.base_model_id,
            display_name=job.base_model_id,
            params_b=check.params_b or 8.0,
            license=job.base_model_license or "unknown",
            train_mode=job.train_mode,  # type: ignore[arg-type]
            fits_t4="unconfirmed",
            vram_gb=0,
            sec_per_step=5.0,
            startup_min=3.0,
        )
    await cancel_job(db, job)
    result = await get_backend(body.backend).submit_job(
        db, project, model, job.preset, Hyperparams(**job.hyperparams), is_llama=job.is_llama
    )
    await db.commit()
    if result.after_commit is not None:
        result.after_commit()
    return TrainingCreated(job=await job_out(db, result.job), token=None, notebook_url=None)


@router.get("/projects/{project_id}/training/{job_id}")
async def get_training(job_id: uuid.UUID, project: OwnedProject, db: DB) -> TrainingJobOut:
    return await job_out(db, await _job(db, project.id, job_id))


@router.get("/projects/{project_id}/training/{job_id}/metrics")
async def training_metrics(job_id: uuid.UUID, project: OwnedProject, db: DB) -> list[MetricOut]:
    job = await _job(db, project.id, job_id)
    rows = await db.scalars(select(TrainingMetric).where(TrainingMetric.job_id == job.id).order_by(TrainingMetric.step))
    return [MetricOut.model_validate(r) for r in rows]


@router.post("/projects/{project_id}/training/{job_id}/token")
async def rotate_token(job_id: uuid.UUID, project: LockedProject, db: DB) -> TokenOut:
    job = await _job(db, project.id, job_id)
    if job.state not in (JobState.created, JobState.running, JobState.paused):
        raise Conflict("This job no longer accepts a notebook.", code="invalid_state")
    if job.backend != "colab":
        raise Conflict("DocTune manages this run's access automatically.", code="token_managed")
    token, row = await jobauth.issue(db, job.id)
    await db.commit()
    return TokenOut(token=token, expires_at=row.expires_at)


@router.post("/projects/{project_id}/training/{job_id}/cancel")
async def cancel_training(job_id: uuid.UUID, project: LockedProject, db: DB) -> ProjectOut:
    job = await _job(db, project.id, job_id)
    if job.state not in (JobState.created, JobState.running, JobState.paused):
        raise Conflict("This job can't be cancelled now.", code="invalid_state")
    await get_backend(job.backend).cancel(db, job)
    await project_service.transition(db, project, ProjectStatus.in_review, actor=Actor.user)
    return await project_out(db, project)


@router.get("/projects/{project_id}/training/{job_id}/checkpoint/download")
async def checkpoint_download(job_id: uuid.UUID, project: OwnedProject, db: DB, storage: StorageDep) -> DownloadOut:
    job = await _job(db, project.id, job_id)
    ckpt = await db.get(Checkpoint, job.id)
    if ckpt is None:
        raise NotFound("No checkpoint yet")
    url = storage.presign_get(ckpt.storage_key, filename=f"checkpoint-{ckpt.step}.zip")
    return DownloadOut(url=url.url, expires_at=url.expires_at)


@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(project: OwnedProject, db: DB) -> list[ArtifactOut]:
    rows = await db.scalars(
        select(Artifact)
        .join(TrainingJob, TrainingJob.id == Artifact.job_id)
        .where(TrainingJob.project_id == project.id, Artifact.uploaded)
        .order_by(Artifact.created_at.desc())
    )
    return [ArtifactOut.model_validate(a) for a in rows]


@router.get("/projects/{project_id}/artifacts/{artifact_id}/download")
async def artifact_download(artifact_id: uuid.UUID, project: OwnedProject, db: DB, storage: StorageDep) -> DownloadOut:
    art = await db.get(Artifact, artifact_id)
    job = await db.get(TrainingJob, art.job_id) if art else None
    if art is None or job is None or job.project_id != project.id or not art.uploaded:
        raise NotFound("Artifact not found")
    name = art.storage_key.rsplit("/", 1)[-1]
    url = storage.presign_get(art.storage_key, filename=f"{project.name[:40]}-{name}".replace(" ", "_"))
    return DownloadOut(url=url.url, expires_at=url.expires_at)


@router.get("/projects/{project_id}/evaluation")
async def get_evaluation(project: OwnedProject, db: DB) -> EvaluationOut | None:
    row = await db.scalar(
        select(Evaluation)
        .join(TrainingJob, TrainingJob.id == Evaluation.job_id)
        .where(TrainingJob.project_id == project.id)
        .order_by(Evaluation.created_at.desc())
        .limit(1)
    )
    return EvaluationOut.model_validate(row) if row else None


def notebook_url() -> str:
    return get_settings().notebook_url
