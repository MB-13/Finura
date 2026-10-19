import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from doctune.core.db import Base, TimestampMixin
from doctune.models.document import EMBEDDING_DIM
from doctune.models.enums import pg_enum


class Provider(StrEnum):
    groq = "groq"
    gemini = "gemini"
    cerebras = "cerebras"


class KeyStatus(StrEnum):
    unverified = "unverified"
    valid = "valid"
    invalid = "invalid"
    quota_exhausted = "quota_exhausted"


class GenKind(StrEnum):
    preview = "preview"
    full = "full"


class GenState(StrEnum):
    queued = "queued"
    running = "running"
    waiting_quota = "waiting_quota"
    finalizing = "finalizing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class UnitState(StrEnum):
    pending = "pending"
    queued = "queued"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class PairOrigin(StrEnum):
    generated = "generated"
    user_added = "user_added"


class PairSplit(StrEnum):
    unassigned = "unassigned"
    train = "train"
    eval = "eval"


class ProviderKey(TimestampMixin, Base):
    __tablename__ = "provider_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_keys_user_id_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[Provider] = mapped_column(pg_enum(Provider, "provider"))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    last4: Mapped[str] = mapped_column(Text)
    status: Mapped[KeyStatus] = mapped_column(
        pg_enum(KeyStatus, "key_status"), default=KeyStatus.unverified, server_default="unverified"
    )
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    default_model: Mapped[str | None] = mapped_column(Text)
    terms_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StyleConfig(Base):
    """Immutable snapshot of a project's style. Editing the style creates a new row."""

    __tablename__ = "style_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    template_key: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    length: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    examples: Mapped[list[dict[str, str]]] = mapped_column(JSONB)
    system_prompt_in_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # the shape of each training example (see doctune.datasets.formats); `format` is the answer format
    dataset_format: Mapped[str] = mapped_column(Text, default="qa_chat", server_default="qa_chat")
    content_hash: Mapped[str] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GenerationRun(TimestampMixin, Base):
    __tablename__ = "generation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    style_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("style_configs.id", ondelete="CASCADE"))
    kind: Mapped[GenKind] = mapped_column(pg_enum(GenKind, "gen_kind"))
    state: Mapped[GenState] = mapped_column(pg_enum(GenState, "gen_state"), default=GenState.queued)
    prompt_version: Mapped[str] = mapped_column(Text)
    pairs_per_chunk: Mapped[int] = mapped_column(SmallInteger)
    target_pairs: Mapped[int] = mapped_column(Integer)
    provider_chain: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    done_chunks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pairs_generated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    pairs_kept: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    resume_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GenerationUnit(Base):
    """One chunk's work inside a run: generate pairs, then judge them. Makes fan-out idempotent."""

    __tablename__ = "generation_units"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[UnitState] = mapped_column(pg_enum(UnitState, "unit_state"), default=UnitState.pending)
    generated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    judged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class DatasetPair(TimestampMixin, Base):
    __tablename__ = "dataset_pairs"
    __table_args__ = (Index("ix_dataset_pairs_project_split_kept", "project_id", "split", "kept"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    origin: Mapped[PairOrigin] = mapped_column(pg_enum(PairOrigin, "pair_origin"), default=PairOrigin.generated)
    # preview samples are shown during style tuning but never become part of the dataset
    preview: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # question/answer are the first prompt and last response for every format; `record` holds the rest
    # (an instruction's input, the turns between in a conversation). Only formats.apply writes these.
    dataset_format: Mapped[str] = mapped_column(Text, default="qa_chat", server_default="qa_chat")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    record: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    judge_correctness: Mapped[int | None] = mapped_column(SmallInteger)
    judge_style: Mapped[int | None] = mapped_column(SmallInteger)
    judge_reason: Mapped[str | None] = mapped_column(Text)
    kept: Mapped[bool | None] = mapped_column(Boolean)
    dropped_reason: Mapped[str | None] = mapped_column(Text)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    split: Mapped[PairSplit] = mapped_column(
        pg_enum(PairSplit, "pair_split"), default=PairSplit.unassigned, server_default="unassigned"
    )
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_dataset_versions_project_id_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    train_count: Mapped[int] = mapped_column(Integer)
    eval_count: Mapped[int] = mapped_column(Integer)
    train_key: Mapped[str] = mapped_column(Text)
    eval_key: Mapped[str] = mapped_column(Text)
    sha256_train: Mapped[str] = mapped_column(Text)
    sha256_eval: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    dataset_format: Mapped[str] = mapped_column(Text, default="qa_chat", server_default="qa_chat")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
