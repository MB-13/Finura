"""Pluggable training compute (design doc): every backend implements this interface.

Colab (user runs our notebook) and Kaggle (we launch it in the user's own Kaggle account, ADR-0002) exist today;
another backend can be added without touching the rest of the system.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from doctune.models.project import Project
from doctune.models.training import Artifact, JobState, TrainingJob
from doctune.training.catalog import BaseModel
from doctune.training.presets import Hyperparams


@dataclass
class SubmitResult:
    job: TrainingJob
    token: str | None  # the one-time secret the user pastes into the notebook (Colab backend)
    launch_url: str | None
    after_commit: Callable[[], None] | None = None  # e.g. enqueue the launch once the job row is committed


class TrainingBackend(Protocol):
    name: str

    async def submit_job(
        self, db: AsyncSession, project: Project, model: BaseModel, preset: str, hp: Hyperparams, *, is_llama: bool
    ) -> SubmitResult: ...

    async def get_status(self, db: AsyncSession, job: TrainingJob) -> JobState: ...

    async def get_output(self, db: AsyncSession, job: TrainingJob) -> list[Artifact]: ...

    async def cancel(self, db: AsyncSession, job: TrainingJob) -> None: ...
