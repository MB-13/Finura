import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.auth import CurrentUserDep
from doctune.core.db import get_session
from doctune.core.storage import Storage, get_storage
from doctune.models.project import Project
from doctune.services import projects as project_service

DB = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]


async def owned_project(project_id: uuid.UUID, user: CurrentUserDep, db: DB) -> Project:
    return await project_service.get_owned(db, project_id, user.id)


async def owned_project_locked(project_id: uuid.UUID, user: CurrentUserDep, db: DB) -> Project:
    """For state-changing routes: row lock so concurrent requests can't race a transition."""
    return await project_service.get_owned(db, project_id, user.id, for_update=True)


OwnedProject = Annotated[Project, Depends(owned_project)]
LockedProject = Annotated[Project, Depends(owned_project_locked)]
