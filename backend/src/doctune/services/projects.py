"""Project service: ownership checks, CRUD, and the single place that changes project status."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from doctune.core import events
from doctune.core.errors import Conflict, LimitExceeded, NotFound
from doctune.models.document import Chunk, Document
from doctune.models.enums import ProjectStatus
from doctune.models.project import Project, ProjectEvent
from doctune.services.transitions import Actor, InvalidTransitionError, check

MAX_ACTIVE_PROJECTS = 20


class InvalidTransition(Conflict):
    code = "invalid_transition"


def _owned(project_id: uuid.UUID, user_id: uuid.UUID) -> Select[Project]:
    return select(Project).where(Project.id == project_id, Project.user_id == user_id, Project.deleted_at.is_(None))


async def get_owned(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, *, for_update: bool = False
) -> Project:
    """Not found and not owned look the same to the caller (no existence leaks)."""
    stmt = _owned(project_id, user_id)
    if for_update:
        stmt = stmt.with_for_update()
    project = (await db.execute(stmt)).scalar_one_or_none()
    if project is None:
        raise NotFound("Project not found")
    return project


async def create(db: AsyncSession, user_id: uuid.UUID, name: str) -> Project:
    active = await db.scalar(
        select(func.count()).select_from(Project).where(Project.user_id == user_id, Project.deleted_at.is_(None))
    )
    if (active or 0) >= MAX_ACTIVE_PROJECTS:
        raise LimitExceeded(f"You can have up to {MAX_ACTIVE_PROJECTS} projects. Delete one to create another.")
    project = Project(user_id=user_id, name=name.strip(), status=ProjectStatus.draft)
    db.add(project)
    await db.flush()
    db.add(ProjectEvent(project_id=project.id, type="created", to_status=ProjectStatus.draft, actor=Actor.user))
    await db.commit()
    await db.refresh(project)
    return project


async def list_for_user(db: AsyncSession, user_id: uuid.UUID, *, limit: int, cursor: datetime | None) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.user_id == user_id, Project.deleted_at.is_(None))
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(Project.updated_at < cursor)
    return list((await db.execute(stmt)).scalars())


async def counts(db: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    docs = await db.scalar(select(func.count()).select_from(Document).where(Document.project_id == project_id))
    chunks = await db.scalar(select(func.count()).select_from(Chunk).where(Chunk.project_id == project_id))
    return {"documents": docs or 0, "chunks": chunks or 0}


def _apply(
    project: Project,
    to: ProjectStatus,
    actor: Actor,
    reason: str | None,
    message: str | None,
    retry_to: ProjectStatus | None,
) -> ProjectEvent:
    from_status = project.status
    try:
        check(from_status, to, actor)
    except InvalidTransitionError as exc:
        raise InvalidTransition(str(exc), details={"from": from_status, "to": to}) from exc
    project.status = to
    project.status_reason = reason
    project.status_message = message
    project.status_retry_to = retry_to if to == ProjectStatus.failed else None
    project.status_changed_at = datetime.now(UTC)
    return ProjectEvent(
        project_id=project.id,
        type="status",
        from_status=from_status,
        to_status=to,
        actor=actor,
        data={"reason": reason} if reason else None,
    )


def _publish(project: Project) -> None:
    events.publish(
        project.id,
        "status",
        {
            "status": project.status,
            "reason": project.status_reason,
            "message": project.status_message,
            "at": project.status_changed_at.isoformat(),
        },
    )


async def transition(
    db: AsyncSession,
    project: Project,
    to: ProjectStatus,
    *,
    actor: Actor,
    reason: str | None = None,
    message: str | None = None,
    retry_to: ProjectStatus | None = None,
    commit: bool = True,
) -> Project:
    """Change status (API side). Callers load the project with `for_update=True` first."""
    db.add(_apply(project, to, actor, reason, message, retry_to))
    if commit:
        await db.commit()
        _publish(project)
    return project


def transition_sync(
    db: Session,
    project_id: uuid.UUID,
    to: ProjectStatus,
    *,
    actor: Actor,
    reason: str | None = None,
    message: str | None = None,
    retry_to: ProjectStatus | None = None,
    if_status: ProjectStatus | None = None,
) -> Project | None:
    """Change status from a worker. Locks the row; with `if_status`, silently skips if the
    project has already moved on (e.g. the user cancelled while the task ran)."""
    project = db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
    if project is None or project.deleted_at is not None:
        db.rollback()
        return None
    if if_status is not None and project.status != if_status:
        db.rollback()
        return None
    db.add(_apply(project, to, actor, reason, message, retry_to))
    db.commit()
    _publish(project)
    return project


def log_event(
    db: AsyncSession | Session, project_id: uuid.UUID, type_: str, actor: Actor, data: dict[str, Any]
) -> None:
    db.add(ProjectEvent(project_id=project_id, type=type_, actor=actor, data=data))
