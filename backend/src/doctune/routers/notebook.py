"""Endpoints the Colab notebook calls with its one-job token (`Authorization: Bearer dtj_...`)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core import events, jobauth
from doctune.core.config import get_settings
from doctune.core.errors import AppError, Conflict
from doctune.core.jobauth import CurrentJobDep
from doctune.core.ratelimit import limit
from doctune.core.storage import Storage
from doctune.models.enums import ProjectStatus
from doctune.models.generation import DatasetVersion
from doctune.models.project import Project
from doctune.models.training import (
    Artifact,
    ArtifactKind,
    Checkpoint,
    EvalState,
    Evaluation,
    JobState,
    PauseReason,
    TrainingJob,
    TrainingMetric,
)
from doctune.routers.deps import DB, StorageDep
from doctune.schemas.training import (
    ArtifactUploadComplete,
    ArtifactUploadRequest,
    CheckpointLatest,
    DatasetRef,
    FailIn,
    FinishIn,
    HeartbeatIn,
    HeartbeatOut,
    JobConfig,
    Ok,
    PauseIn,
    StartIn,
    TrainingCompleteIn,
    UploadComplete,
    UploadRequest,
    UploadUrl,
)
from doctune.services import projects as project_service
from doctune.services.transitions import Actor
from doctune.training.colab import EVAL_MAX_ITEMS, NOTEBOOK_MIN_VERSION
from doctune.training.presets import Hyperparams

router = APIRouter(prefix="/jobs/current", tags=["notebook"], dependencies=[Depends(limit("notebook", 120))])

MAX_CHECKPOINT = 1536 * 1024 * 1024
MAX_ARTIFACT = {"adapter_safetensors": 1024 * 1024 * 1024, "eval_generations": 20 * 1024 * 1024}
HEARTBEAT_SECONDS = 30
METRIC_POINTS = 400

PAUSE_MESSAGES = {
    PauseReason.session_ended: "Your Colab session ended at {pct}%. Progress is saved. Open the notebook and run it "
    "again to continue.",
    PauseReason.idle_timeout: "Colab disconnected because the tab was idle. Progress is saved at {pct}%. Run the "
    "notebook again and keep the tab open.",
    PauseReason.no_gpu: "Colab has no free GPU for your account right now. Progress is saved at {pct}%. "
    "Try again later.",
    PauseReason.stopped: "Training stopped at {pct}%. Progress is saved. Run the notebook again to continue.",
    PauseReason.user_stopped: "You stopped training at {pct}%. Progress is saved. Run the notebook again to continue.",
    PauseReason.heartbeat_timeout: "Training stopped at {pct}%. Progress is saved. Run the notebook again to continue.",
}


class NotebookOutdated(AppError):
    status_code, code = 426, "notebook_outdated"


KAGGLE_PAUSE_MESSAGES = {
    PauseReason.no_gpu: "Kaggle has no free GPU for your account right now. Progress is saved at {pct}%. "
    "DocTune will try again automatically.",
}
KAGGLE_PAUSE_DEFAULT = "Your Kaggle session ended at {pct}%. Progress is saved; DocTune restarts it automatically."


def pause_message(reason: PauseReason, step: int, max_steps: int, backend: str = "colab") -> str:
    pct = int(100 * step / max_steps) if max_steps else 0
    if backend == "kaggle":
        return KAGGLE_PAUSE_MESSAGES.get(reason, KAGGLE_PAUSE_DEFAULT).format(pct=pct)
    return PAUSE_MESSAGES[reason].format(pct=pct)


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except ValueError:
        return (0,)


def _keys(job: TrainingJob) -> dict[str, str]:
    base = f"j/{job.id}"
    return {
        "checkpoint": f"{base}/checkpoint/latest.zip",
        "adapter_safetensors": f"{base}/adapter/adapter.zip",
        "eval_generations": f"{base}/eval/generations.jsonl",
    }


async def _project(db: AsyncSession, job: TrainingJob) -> Project:
    project = await db.get(Project, job.project_id, with_for_update=True)
    if project is None or project.deleted_at is not None:
        raise Conflict("This project was deleted.", code="project_deleted")
    return project


def _project_url(job: TrainingJob) -> str:
    return f"{get_settings().web_origin}/projects/{job.project_id}"


async def _resume_if_paused(db: AsyncSession, job: TrainingJob, project: Project) -> None:
    """A start/heartbeat from a paused job means the user re-ran the notebook."""
    from doctune.workers.tasks.notify import send_email

    was_paused_at = job.paused_at
    if job.state in (JobState.created, JobState.paused):
        job.state = JobState.running
        job.pause_reason, job.paused_at = None, None
    if project.status in (ProjectStatus.awaiting_run, ProjectStatus.paused):
        await project_service.transition(db, project, ProjectStatus.training, actor=Actor.notebook, commit=False)
        if was_paused_at and datetime.now(UTC) - was_paused_at > timedelta(hours=1):
            send_email.delay("resumed", str(job.project_id), f"job:{job.id}:resume:{job.current_step}")


async def _commit_and_publish(db: AsyncSession, project: Project) -> None:
    await db.commit()
    events.publish(
        project.id,
        "status",
        {
            "status": project.status,
            "reason": project.status_reason,
            "message": project.status_message,
            "at": project.status_changed_at.isoformat(),
        },
    )


@router.get("/config")
async def job_config(
    current: CurrentJobDep, db: DB, storage: StorageDep, notebook_version: str | None = None
) -> JobConfig:
    job = current.job
    if notebook_version and _version_tuple(notebook_version) < _version_tuple(NOTEBOOK_MIN_VERSION):
        raise NotebookOutdated(f"This notebook is outdated. Open the latest one: {get_settings().notebook_url}")
    project = await db.get(Project, job.project_id)
    version = await db.get(DatasetVersion, job.dataset_version_id)
    assert project is not None and version is not None
    ttl = 6 * 3600
    await db.commit()
    return JobConfig(
        job_id=job.id,
        project_name=project.name,
        base_model_id=job.base_model_id,
        base_model_license=job.base_model_license,
        is_llama=job.is_llama,
        train_mode=job.train_mode,
        hyperparams=Hyperparams.model_validate(job.hyperparams),
        seed=job.seed,
        max_steps=job.max_steps,
        lib_versions=job.lib_versions,
        dataset=DatasetRef(
            train_url=storage.presign_get(version.train_key, ttl=ttl).url,
            eval_url=storage.presign_get(version.eval_key, ttl=ttl).url,
            sha256_train=version.sha256_train,
            sha256_eval=version.sha256_eval,
            train_count=version.train_count,
            eval_count=version.eval_count,
            system_prompt=version.system_prompt,
        ),
        checkpoint_every_minutes=int(job.hyperparams.get("checkpoint_minutes", 7)),
        heartbeat_every_seconds=HEARTBEAT_SECONDS,
        eval_max_items=EVAL_MAX_ITEMS,
        notebook_min_version=NOTEBOOK_MIN_VERSION,
        project_url=_project_url(job),
    )


@router.post("/start")
async def start(body: StartIn, current: CurrentJobDep, db: DB) -> Ok:
    job = current.job
    if job.state in (JobState.completed, JobState.failed, JobState.cancelled):
        raise Conflict("This job has already ended.", code="job_ended")
    project = await _project(db, job)
    job.runtime_info = body.runtime.model_dump()
    job.started_at = job.started_at or datetime.now(UTC)
    job.last_heartbeat_at = datetime.now(UTC)
    await _resume_if_paused(db, job, project)
    await _commit_and_publish(db, project)
    return Ok(project_url=_project_url(job))


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn, current: CurrentJobDep, db: DB) -> HeartbeatOut:
    job = current.job
    if job.state in (JobState.completed, JobState.failed, JobState.cancelled):
        return HeartbeatOut(ok=False, cancel_requested=True)
    project = await _project(db, job)
    job.current_step, job.max_steps = body.step, body.max_steps
    job.last_loss = body.loss if body.loss is not None else job.last_loss
    job.last_heartbeat_at = datetime.now(UTC)
    if job.state != JobState.evaluating:
        await _resume_if_paused(db, job, project)
    every = max(1, body.max_steps // METRIC_POINTS)
    if body.loss is not None and (body.step % every == 0 or body.step == body.max_steps):
        await db.execute(
            insert(TrainingMetric)
            .values(job_id=job.id, step=body.step, loss=body.loss, lr=body.lr)
            .on_conflict_do_update(index_elements=["job_id", "step"], set_={"loss": body.loss, "lr": body.lr})
        )
    await db.commit()
    events.publish(
        job.project_id,
        "train_metrics",
        {
            "job_id": str(job.id),
            "step": body.step,
            "max_steps": body.max_steps,
            "loss": body.loss,
            "lr": body.lr,
            "at": datetime.now(UTC),
        },
    )
    return HeartbeatOut()


@router.get("/checkpoint/latest")
async def checkpoint_latest(current: CurrentJobDep, db: DB, storage: StorageDep) -> CheckpointLatest:
    ckpt = await db.get(Checkpoint, current.job.id)
    await db.commit()
    if ckpt is None or storage.head(ckpt.storage_key) is None:
        return CheckpointLatest(exists=False)
    return CheckpointLatest(
        exists=True, step=ckpt.step, url=storage.presign_get(ckpt.storage_key, ttl=3600).url, sha256=ckpt.sha256
    )


def _upload_url(storage: Storage, key: str, size: int, content_type: str, ttl: int) -> UploadUrl:
    signed = storage.presign_put(key, content_type=content_type, max_bytes=size, ttl=ttl)
    return UploadUrl(url=signed.url, headers=signed.headers, expires_at=signed.expires_at)


@router.post("/checkpoint/upload-url")
async def checkpoint_upload_url(body: UploadRequest, current: CurrentJobDep, db: DB, storage: StorageDep) -> UploadUrl:
    await db.commit()
    if body.size_bytes > MAX_CHECKPOINT:
        raise Conflict("Checkpoint is larger than allowed (1.5 GB).", code="too_large")
    # each upload goes to a staging key, then replaces `latest` on complete (a failed upload never
    # destroys the previous checkpoint)
    key = f"j/{current.job.id}/checkpoint/upload.zip"
    return _upload_url(storage, key, body.size_bytes, "application/zip", ttl=3600)


@router.post("/checkpoint/complete")
async def checkpoint_complete(body: UploadComplete, current: CurrentJobDep, db: DB, storage: StorageDep) -> Ok:
    job = current.job
    staging, latest = f"j/{job.id}/checkpoint/upload.zip", _keys(job)["checkpoint"]
    info = storage.head(staging)
    if info is None or info.size != body.size_bytes:
        raise Conflict("Checkpoint upload is missing or incomplete.", code="upload_mismatch")
    storage.write_bytes(latest, storage.read_bytes(staging))  # LocalStorage; R2 will use copy_object
    storage.delete(staging)
    await db.execute(
        insert(Checkpoint)
        .values(
            job_id=job.id,
            step=body.step or job.current_step,
            storage_key=latest,
            size_bytes=body.size_bytes,
            sha256=body.sha256,
        )
        .on_conflict_do_update(
            index_elements=["job_id"],
            set_={
                "step": body.step or job.current_step,
                "size_bytes": body.size_bytes,
                "sha256": body.sha256,
                "uploaded_at": datetime.now(UTC),
            },
        )
    )
    await db.commit()
    events.publish(job.project_id, "progress", {"phase": "checkpoint", "step": body.step})
    return Ok()


def _prepare_checkpoint_for_playground(job: TrainingJob) -> None:
    from doctune.workers.tasks.models import convert_adapter

    convert_adapter.delay(str(job.id), "checkpoint")


@router.post("/pause")
async def pause(body: PauseIn, current: CurrentJobDep, db: DB) -> Ok:
    job = current.job
    if job.state not in (JobState.running, JobState.created):
        await db.commit()
        return Ok()
    from doctune.workers.tasks.notify import send_email

    project = await _project(db, job)
    reason = PauseReason(body.reason)
    step = body.step if body.step is not None else job.current_step
    job.state, job.pause_reason, job.paused_at = JobState.paused, reason, datetime.now(UTC)
    if project.status in (ProjectStatus.training, ProjectStatus.awaiting_run):
        message = pause_message(reason, step, job.max_steps, job.backend)
        await project_service.transition(
            db, project, ProjectStatus.paused, actor=Actor.notebook, reason=reason.value, message=message, commit=False
        )
        await _commit_and_publish(db, project)
        _prepare_checkpoint_for_playground(job)
        # Kaggle relaunches interrupted runs by itself, so only email when it won't (attempts used up)
        if job.backend == "colab" or job.launch_attempts >= 3:
            send_email.delay(
                "paused",
                str(job.project_id),
                f"job:{job.id}:pause:{step}",
                {"message": message, "percent": str(int(100 * step / max(job.max_steps, 1)))},
            )
    else:
        await db.commit()
    return Ok()


@router.post("/training-complete")
async def training_complete(body: TrainingCompleteIn, current: CurrentJobDep, db: DB) -> Ok:
    job = current.job
    project = await _project(db, job)
    job.current_step = body.final_step
    job.last_loss = body.final_loss if body.final_loss is not None else job.last_loss
    job.metrics = {**(job.metrics or {}), "train_runtime_s": body.train_runtime_s, "final_loss": body.final_loss}
    if project.status == ProjectStatus.paused:
        await project_service.transition(db, project, ProjectStatus.training, actor=Actor.notebook, commit=False)
    if project.status == ProjectStatus.training:
        job.state = JobState.evaluating
        await project_service.transition(db, project, ProjectStatus.evaluating, actor=Actor.notebook, commit=False)
    await _commit_and_publish(db, project)
    return Ok()


@router.post("/artifacts/upload-url")
async def artifact_upload_url(
    body: ArtifactUploadRequest, current: CurrentJobDep, db: DB, storage: StorageDep
) -> UploadUrl:
    await db.commit()
    if body.size_bytes > MAX_ARTIFACT[body.kind]:
        raise Conflict("This file is larger than allowed.", code="too_large")
    content_type = "application/zip" if body.kind == "adapter_safetensors" else "application/x-ndjson"
    return _upload_url(storage, _keys(current.job)[body.kind], body.size_bytes, content_type, ttl=3600)


@router.post("/artifacts/complete")
async def artifact_complete(body: ArtifactUploadComplete, current: CurrentJobDep, db: DB, storage: StorageDep) -> Ok:
    job = current.job
    key = _keys(job)[body.kind]
    info = storage.head(key)
    if info is None or info.size != body.size_bytes:
        raise Conflict("Upload is missing or incomplete.", code="upload_mismatch")
    kind = ArtifactKind(body.kind)
    existing = await db.scalar(select(Artifact).where(Artifact.job_id == job.id, Artifact.kind == kind))
    art = existing or Artifact(job_id=job.id, kind=kind, storage_key=key)
    art.size_bytes, art.sha256, art.uploaded = body.size_bytes, body.sha256, True
    db.add(art)
    if kind == ArtifactKind.eval_generations:
        evaluation = await db.scalar(select(Evaluation).where(Evaluation.job_id == job.id))
        if evaluation is None:
            db.add(Evaluation(job_id=job.id, state=EvalState.pending))
    await db.commit()
    from doctune.workers.tasks.models import convert_adapter, score_evaluation

    if kind == ArtifactKind.adapter_safetensors:
        convert_adapter.delay(str(job.id), "final")
    else:
        score_evaluation.delay(str(job.id))
    return Ok()


@router.post("/finish")
async def finish(body: FinishIn, current: CurrentJobDep, db: DB) -> Ok:
    job = current.job
    adapter = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job.id, Artifact.kind == ArtifactKind.adapter_safetensors, Artifact.uploaded
        )
    )
    if adapter is None:
        raise Conflict("Upload the adapter before finishing.", code="adapter_missing")
    project = await _project(db, job)
    job.metrics = {**(job.metrics or {}), **body.metrics}
    job.exports = {k: v for k, v in body.exports.items() if v}
    job.state = JobState.completed
    job.completed_at = job.ended_at = datetime.now(UTC)
    if job.backend != "colab":
        await jobauth.revoke_all(db, job.id)  # automatic backends: the run is over, so is its access
    if project.status == ProjectStatus.training:
        await project_service.transition(db, project, ProjectStatus.evaluating, actor=Actor.notebook, commit=False)
    if project.status == ProjectStatus.evaluating:
        await project_service.transition(db, project, ProjectStatus.ready, actor=Actor.notebook, commit=False)
    await _commit_and_publish(db, project)
    from doctune.workers.tasks.notify import send_email

    send_email.delay("training_finished", str(job.project_id), f"job:{job.id}:finished")
    return Ok(project_url=_project_url(job))


@router.post("/fail")
async def fail(body: FailIn, current: CurrentJobDep, db: DB) -> Ok:
    job = current.job
    if not body.fatal:
        return await pause(PauseIn(reason="stopped", step=body.step), current, db)
    from doctune.workers.tasks.notify import send_email

    project = await _project(db, job)
    job.state, job.error, job.ended_at = JobState.failed, body.error[:2000], datetime.now(UTC)
    if job.backend != "colab":
        await jobauth.revoke_all(db, job.id)
    message = f"Training failed: {body.error[:300]}"
    if "out_of_memory" in body.error:
        message = "The GPU ran out of memory. Try a smaller model or the Quick preset."
    if project.status in (ProjectStatus.training, ProjectStatus.evaluating, ProjectStatus.paused):
        if project.status == ProjectStatus.paused:
            await project_service.transition(db, project, ProjectStatus.training, actor=Actor.notebook, commit=False)
        await project_service.transition(
            db,
            project,
            ProjectStatus.failed,
            actor=Actor.notebook,
            reason="training_failed",
            message=message,
            retry_to=ProjectStatus.in_review,
            commit=False,
        )
    await _commit_and_publish(db, project)
    send_email.delay("job_failed", str(job.project_id), f"job:{job.id}:failed", {"message": message})
    return Ok()
