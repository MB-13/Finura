import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from doctune.models.enums import ProjectStatus
from doctune.schemas.generation import DatasetVersionOut, RunOut, StyleOut
from doctune.schemas.training import EvaluationOut, TrainingJobOut


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_pairs: int | None = Field(default=None, ge=50, le=2000)
    gen_provider: Literal["groq", "gemini", "cerebras"] | None = None
    gen_model: str | None = Field(default=None, max_length=200)


class ProjectCounts(BaseModel):
    documents: int = 0
    chunks: int = 0
    pairs_kept: int = 0
    pairs_train: int = 0
    pairs_eval: int = 0


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: ProjectStatus
    status_message: str | None
    base_model_id: str | None
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummary):
    status_reason: str | None
    status_changed_at: datetime
    base_model_license: str | None
    gen_provider: str | None
    gen_model: str | None
    target_pairs: int
    total_bytes: int
    counts: ProjectCounts
    allowed_actions: list[str]
    style: StyleOut | None = None
    latest_preview: RunOut | None = None
    active_run: RunOut | None = None
    dataset_version: DatasetVersionOut | None = None
    active_job: TrainingJobOut | None = None
    evaluation: EvaluationOut | None = None


class ProjectEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    from_status: ProjectStatus | None
    to_status: ProjectStatus | None
    actor: str
    data: dict[str, Any] | None
    at: datetime
