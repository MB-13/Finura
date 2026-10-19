"""All models are imported here so Alembic autogenerate sees them."""

from doctune.models.compute import ComputeAccount
from doctune.models.document import Chunk, Document
from doctune.models.enums import DocumentStatus, ProjectStatus
from doctune.models.generation import (
    DatasetPair,
    DatasetVersion,
    GenerationRun,
    GenerationUnit,
    ProviderKey,
    StyleConfig,
)
from doctune.models.project import Project, ProjectEvent
from doctune.models.training import Artifact, Checkpoint, Evaluation, JobToken, TrainingJob, TrainingMetric
from doctune.models.user import EmailLog, User

__all__ = [
    "Artifact",
    "Checkpoint",
    "Chunk",
    "ComputeAccount",
    "DatasetPair",
    "DatasetVersion",
    "Document",
    "DocumentStatus",
    "EmailLog",
    "Evaluation",
    "GenerationRun",
    "GenerationUnit",
    "JobToken",
    "Project",
    "ProjectEvent",
    "ProjectStatus",
    "ProviderKey",
    "StyleConfig",
    "TrainingJob",
    "TrainingMetric",
    "User",
]
