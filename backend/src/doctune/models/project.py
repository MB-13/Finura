import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from doctune.core.db import Base, TimestampMixin
from doctune.models.enums import ProjectStatus, pg_enum

project_status_enum = pg_enum(ProjectStatus, "project_status")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_user_id_updated_at", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[ProjectStatus] = mapped_column(
        project_status_enum, default=ProjectStatus.draft, server_default="draft", index=True
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_message: Mapped[str | None] = mapped_column(Text)
    status_retry_to: Mapped[ProjectStatus | None] = mapped_column(project_status_enum)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    base_model_id: Mapped[str | None] = mapped_column(Text)
    base_model_license: Mapped[str | None] = mapped_column(Text)
    base_model_is_custom: Mapped[bool] = mapped_column(default=False, server_default="false")
    license_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gen_provider: Mapped[str | None] = mapped_column(Text)
    gen_model: Mapped[str | None] = mapped_column(Text)
    style_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # set when the dataset is approved; any edit afterwards clears it (approve again)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    target_pairs: Mapped[int] = mapped_column(Integer, default=500, server_default="500")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectEvent(Base):
    __tablename__ = "project_events"
    __table_args__ = (Index("ix_project_events_project_id_at", "project_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(Text)
    from_status: Mapped[ProjectStatus | None] = mapped_column(project_status_enum)
    to_status: Mapped[ProjectStatus | None] = mapped_column(project_status_enum)
    actor: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
