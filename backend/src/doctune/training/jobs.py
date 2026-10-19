"""Pieces shared by every training backend: creating the job row and cancelling it."""

import random
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core import jobauth
from doctune.core.config import get_settings
from doctune.models.generation import DatasetVersion
from doctune.models.project import Project
from doctune.models.training import Artifact, JobState, TrainingJob
from doctune.training.catalog import LIB_VERSIONS, BaseModel
from doctune.training.presets import Hyperparams, max_steps


async def create_job_row(
    db: AsyncSession,
    project: Project,
    model: BaseModel,
    preset: str,
    hp: Hyperparams,
    *,
    is_llama: bool,
    backend: str,
) -> TrainingJob:
    version = await db.get(DatasetVersion, project.dataset_version_id)
    assert version is not None
    job = TrainingJob(
        project_id=project.id,
        user_id=project.user_id,
        dataset_version_id=version.id,
        backend=backend,
        base_model_id=model.id,
        base_model_license=model.license,
        is_llama=is_llama,
        train_mode=model.train_mode,
        preset=preset,
        hyperparams=hp.model_dump(),
        seed=random.SystemRandom().randint(1, 2**31 - 1),
        lib_versions=LIB_VERSIONS,
        notebook_version=get_settings().notebook_version,
        state=JobState.created,
        max_steps=max_steps(version.train_count, hp),
    )
    db.add(job)
    await db.flush()
    return job


async def cancel_job(db: AsyncSession, job: TrainingJob) -> None:
    """Revoking the tokens is what stops a run: the notebook/kernel treats a token error as 'stop'."""
    await jobauth.revoke_all(db, job.id)
    job.state = JobState.cancelled
    job.ended_at = datetime.now(UTC)


async def uploaded_artifacts(db: AsyncSession, job: TrainingJob) -> list[Artifact]:
    return list((await db.scalars(select(Artifact).where(Artifact.job_id == job.id, Artifact.uploaded))).all())
