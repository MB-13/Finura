from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.auth import CurrentUserDep
from doctune.core.db import get_session
from doctune.core.errors import NotFound
from doctune.models.user import User
from doctune.schemas.me import MeOut, MePatch

router = APIRouter(prefix="/me", tags=["me"])

Session = Annotated[AsyncSession, Depends(get_session)]


async def _load(session: AsyncSession, user: CurrentUserDep) -> User:
    row = await session.get(User, user.id)
    if row is None:
        raise NotFound()
    return row


@router.get("")
async def get_me(user: CurrentUserDep, session: Session) -> MeOut:
    return MeOut.model_validate(await _load(session, user))


@router.patch("")
async def patch_me(body: MePatch, user: CurrentUserDep, session: Session) -> MeOut:
    row = await _load(session, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return MeOut.model_validate(row)


@router.delete("", status_code=status.HTTP_202_ACCEPTED)
async def delete_me(user: CurrentUserDep, session: Session) -> None:
    """Delete the account and everything in it (projects, files, keys), then the Supabase login."""
    from datetime import UTC, datetime

    from sqlalchemy import update

    from doctune.models.project import Project
    from doctune.workers.tasks.housekeeping import purge_user

    await session.execute(
        update(Project)
        .where(Project.user_id == user.id, Project.deleted_at.is_(None))
        .values(deleted_at=datetime.now(UTC))
    )
    await session.commit()
    purge_user.delay(str(user.id))
