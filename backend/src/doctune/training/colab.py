"""The Colab backend: the user runs our notebook in their own Google account with a one-job token."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core import jobauth
from doctune.core.config import get_settings
from doctune.models.generation import DatasetPair
from doctune.models.project import Project
from doctune.models.training import Artifact, JobState, TrainingJob
from doctune.parsing.chunker import count_tokens
from doctune.training.base import SubmitResult
from doctune.training.catalog import BaseModel
from doctune.training.jobs import cancel_job, create_job_row, uploaded_artifacts
from doctune.training.presets import Hyperparams, estimate_minutes

NOTEBOOK_MIN_VERSION = "0.1.0"
EVAL_MAX_ITEMS = 100


async def avg_example_tokens(db: AsyncSession, project_id: uuid.UUID) -> float:
    sample = (
        await db.execute(
            select(DatasetPair.question, DatasetPair.answer)
            .where(DatasetPair.project_id == project_id, DatasetPair.kept.is_(True), DatasetPair.preview.is_(False))
            .limit(50)
        )
    ).all()
    if not sample:
        return 200.0
    return sum(count_tokens(q) + count_tokens(a) + 20 for q, a in sample) / len(sample)


class ColabBackend:
    name = "colab"

    async def submit_job(
        self, db: AsyncSession, project: Project, model: BaseModel, preset: str, hp: Hyperparams, *, is_llama: bool
    ) -> SubmitResult:
        job = await create_job_row(db, project, model, preset, hp, is_llama=is_llama, backend=self.name)
        token, _ = await jobauth.issue(db, job.id)
        return SubmitResult(job=job, token=token, launch_url=get_settings().notebook_url)

    async def get_status(self, db: AsyncSession, job: TrainingJob) -> JobState:
        return job.state

    async def get_output(self, db: AsyncSession, job: TrainingJob) -> list[Artifact]:
        return await uploaded_artifacts(db, job)

    async def cancel(self, db: AsyncSession, job: TrainingJob) -> None:
        await cancel_job(db, job)


def job_minutes(model: BaseModel, steps: int, avg_tokens: float) -> float:
    return estimate_minutes(steps, model.sec_per_step, model.startup_min, avg_tokens)


backend = ColabBackend()
