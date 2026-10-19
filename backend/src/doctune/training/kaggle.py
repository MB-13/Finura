"""The Kaggle backend (ADR-0002): a worker pushes a private script kernel to the user's own Kaggle account.

`submit_job` only writes the job row; the launch happens in a Celery task after the request commits. Progress then
flows through the same `/jobs/current/*` job-token API as Colab.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from doctune.models.project import Project
from doctune.models.training import Artifact, JobState, TrainingJob
from doctune.training.base import SubmitResult
from doctune.training.catalog import BaseModel
from doctune.training.jobs import cancel_job, create_job_row, uploaded_artifacts
from doctune.training.presets import Hyperparams


class KaggleBackend:
    name = "kaggle"

    async def submit_job(
        self, db: AsyncSession, project: Project, model: BaseModel, preset: str, hp: Hyperparams, *, is_llama: bool
    ) -> SubmitResult:
        job = await create_job_row(db, project, model, preset, hp, is_llama=is_llama, backend=self.name)
        job_id = str(job.id)

        def enqueue() -> None:
            from doctune.workers.tasks.kaggle import launch_kaggle_job

            launch_kaggle_job.delay(job_id, 1)

        return SubmitResult(job=job, token=None, launch_url=None, after_commit=enqueue)

    async def get_status(self, db: AsyncSession, job: TrainingJob) -> JobState:
        return job.state

    async def get_output(self, db: AsyncSession, job: TrainingJob) -> list[Artifact]:
        return await uploaded_artifacts(db, job)

    async def cancel(self, db: AsyncSession, job: TrainingJob) -> None:
        # no usable Kaggle cancel API: the kernel stops at its next call because its token is revoked
        await cancel_job(db, job)


backend = KaggleBackend()
