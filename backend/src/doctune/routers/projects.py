from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from doctune.core.auth import CurrentUserDep
from doctune.core.errors import Conflict
from doctune.core.ratelimit import limit
from doctune.models.enums import ProjectStatus
from doctune.models.project import ProjectEvent
from doctune.routers.deps import DB, LockedProject, OwnedProject
from doctune.schemas.common import Page
from doctune.schemas.projects import ProjectCreate, ProjectEventOut, ProjectOut, ProjectPatch, ProjectSummary
from doctune.services import documents as document_service
from doctune.services import projects as project_service
from doctune.services.transitions import Actor
from doctune.services.views import project_out

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def list_projects(
    user: CurrentUserDep,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[datetime | None, Query(description="`updated_at` of the last item seen")] = None,
) -> Page[ProjectSummary]:
    rows = await project_service.list_for_user(db, user.id, limit=limit, cursor=cursor)
    items, more = rows[:limit], len(rows) > limit
    return Page(
        items=[ProjectSummary.model_validate(p) for p in items],
        next_cursor=items[-1].updated_at.isoformat() if more and items else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit("create_project", 20))])
async def create_project(body: ProjectCreate, user: CurrentUserDep, db: DB) -> ProjectOut:
    project = await project_service.create(db, user.id, body.name)
    return await project_out(db, project)


@router.get("/{project_id}")
async def get_project(project: OwnedProject, db: DB) -> ProjectOut:
    return await project_out(db, project)


@router.patch("/{project_id}")
async def patch_project(body: ProjectPatch, project: LockedProject, db: DB) -> ProjectOut:
    changes = body.model_dump(exclude_unset=True)
    if "target_pairs" in changes and project.status not in (
        ProjectStatus.draft,
        ProjectStatus.uploaded,
        ProjectStatus.parsing,
        ProjectStatus.awaiting_style,
    ):
        raise Conflict("The dataset size can't change after generation has started.", code="invalid_state")
    for field, value in changes.items():
        setattr(project, field, value.strip() if isinstance(value, str) else value)
    await db.commit()
    await db.refresh(project)
    return await project_out(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_project(project: LockedProject, db: DB) -> None:
    from doctune.workers.tasks.housekeeping import purge_project

    project.deleted_at = datetime.now(UTC)
    await db.commit()
    purge_project.delay(str(project.id))


@router.post("/{project_id}/process", status_code=status.HTTP_202_ACCEPTED)
async def process_documents(project: LockedProject, db: DB) -> ProjectOut:
    from doctune.workers.tasks.parse import parse_document

    docs = await document_service.documents_to_parse(db, project.id)
    if not docs:
        raise Conflict("Upload at least one document first.", code="no_documents")
    await project_service.transition(db, project, ProjectStatus.parsing, actor=Actor.user)
    for doc in docs:
        parse_document.delay(str(doc.id))
    return await project_out(db, project)


@router.post("/{project_id}/retry")
async def retry_project(project: LockedProject, db: DB) -> ProjectOut:
    if project.status != ProjectStatus.failed or project.status_retry_to is None:
        raise Conflict("There's nothing to retry.", code="invalid_state")
    await project_service.transition(db, project, project.status_retry_to, actor=Actor.user)
    return await project_out(db, project)


@router.get("/{project_id}/activity")
async def project_activity(
    project: OwnedProject,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ProjectEventOut]:
    rows = await db.execute(
        select(ProjectEvent)
        .where(ProjectEvent.project_id == project.id)
        .order_by(ProjectEvent.at.desc(), ProjectEvent.id.desc())
        .limit(limit)
    )
    return [ProjectEventOut.model_validate(e) for e in rows.scalars()]
