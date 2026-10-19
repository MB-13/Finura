"""Connected compute accounts (Kaggle): ownership-scoped access and API views."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.models.compute import ComputeAccount
from doctune.schemas.compute import KaggleAccountOut

KAGGLE = "kaggle"


async def get_kaggle(db: AsyncSession, user_id: uuid.UUID) -> ComputeAccount | None:
    return await db.scalar(
        select(ComputeAccount).where(ComputeAccount.user_id == user_id, ComputeAccount.provider == KAGGLE)
    )


def kaggle_out(account: ComputeAccount) -> KaggleAccountOut:
    def hours(seconds: int | None) -> float | None:
        return round(seconds / 3600, 1) if seconds is not None else None

    return KaggleAccountOut(
        username=account.username,
        token_hint=f"…{account.last4}",
        status=account.status,
        status_message=account.status_message,
        gpu_hours_used=hours(account.gpu_used_s),
        gpu_hours_total=hours(account.gpu_total_s),
        quota_refresh_at=account.quota_refresh_at,
        checked_at=account.checked_at,
    )
