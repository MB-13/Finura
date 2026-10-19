import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from doctune.core.db import Base, TimestampMixin
from doctune.models.enums import pg_enum


class JobState(StrEnum):
    created = "created"
    running = "running"
    paused = "paused"
    evaluating = "evaluating"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class PauseReason(StrEnum):
    session_ended = "session_ended"
    idle_timeout = "idle_timeout"
    no_gpu = "no_gpu"
    stopped = "stopped"
    heartbeat_timeout = "heartbeat_timeout"
    user_stopped = "user_stopped"


class ArtifactKind(StrEnum):
    adapter_safetensors = "adapter_safetensors"
    adapter_gguf = "adapter_gguf"
    checkpoint_gguf = "checkpoint_gguf"
    eval_generations = "eval_generations"


class EvalState(StrEnum):
    pending = "pending"
    scoring = "scoring"
    done = "done"
    failed = "failed"


class TrainingJob(TimestampMixin, Base):
    __tablename__ = "training_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    backend: Mapped[str] = mapped_column(Text, default="colab")
    base_model_id: Mapped[str] = mapped_column(Text)
    base_model_license: Mapped[str | None] = mapped_column(Text)
    is_llama: Mapped[bool] = mapped_column(default=False, server_default="false")
    train_mode: Mapped[str] = mapped_column(Text)
    preset: Mapped[str] = mapped_column(Text)
    hyperparams: Mapped[dict[str, Any]] = mapped_column(JSONB)
    seed: Mapped[int] = mapped_column(Integer)
    lib_versions: Mapped[dict[str, str]] = mapped_column(JSONB)
    notebook_version: Mapped[str] = mapped_column(Text)
    state: Mapped[JobState] = mapped_column(pg_enum(JobState, "job_state"), default=JobState.created, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_steps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_loss: Mapped[float | None] = mapped_column(Float)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pause_reason: Mapped[PauseReason | None] = mapped_column(pg_enum(PauseReason, "pause_reason"))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    exports: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # drives 14-day retention
    # automatic backends (Kaggle): how many times the run was launched, and where it lives
    launch_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    external_ref: Mapped[str | None] = mapped_column(Text)  # e.g. the Kaggle kernel slug "user/doctune-ab12-1"
    external_url: Mapped[str | None] = mapped_column(Text)


class JobToken(Base):
    __tablename__ = "job_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    token_prefix: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingMetric(Base):
    __tablename__ = "training_metrics"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[int] = mapped_column(Integer, primary_key=True)
    loss: Mapped[float | None] = mapped_column(Float)
    lr: Mapped[float | None] = mapped_column(Float)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Checkpoint(Base):
    """Only the latest checkpoint per job is kept (same storage key, overwritten)."""

    __tablename__ = "checkpoints"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), primary_key=True)
    step: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[ArtifactKind] = mapped_column(pg_enum(ArtifactKind, "artifact_kind"))
    storage_key: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    uploaded: Mapped[bool] = mapped_column(default=False, server_default="false")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evaluation(TimestampMixin, Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("training_jobs.id", ondelete="CASCADE"), unique=True)
    state: Mapped[EvalState] = mapped_column(pg_enum(EvalState, "eval_state"), default=EvalState.pending)
    n_items: Mapped[int] = mapped_column(Integer, default=0)
    base_scores: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    tuned_scores: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    samples: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
