import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from doctune.core.db import Base, TimestampMixin


class ComputeStatus(StrEnum):
    unchecked = "unchecked"
    ok = "ok"
    invalid = "invalid"
    no_gpu_quota = "no_gpu_quota"


class ComputeAccount(TimestampMixin, Base):
    """A user's own account on an automatic training provider (Kaggle). The token is encrypted at rest."""

    __tablename__ = "compute_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_compute_accounts_user_id_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(Text, default="kaggle", server_default="kaggle")
    username: Mapped[str] = mapped_column(Text)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    last4: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default=ComputeStatus.unchecked, server_default="unchecked")
    status_message: Mapped[str | None] = mapped_column(Text)
    gpu_used_s: Mapped[int | None] = mapped_column(Integer)
    gpu_total_s: Mapped[int | None] = mapped_column(Integer)
    quota_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
