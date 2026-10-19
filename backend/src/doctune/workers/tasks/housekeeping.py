import uuid

import httpx
import structlog
from sqlalchemy import delete, select

from doctune.core import events
from doctune.core.config import get_settings
from doctune.core.db import sync_session
from doctune.core.storage import get_storage
from doctune.models.project import Project
from doctune.models.training import TrainingJob
from doctune.models.user import User
from doctune.workers.celery_app import app

log = structlog.get_logger()


@app.task(name="doctune.workers.tasks.housekeeping.purge_project", max_retries=5, default_retry_delay=60)
def purge_project(project_id: str) -> None:
    """Delete everything a project owns: files first, then rows (FK cascades). Safe to re-run."""
    pid = uuid.UUID(project_id)
    with sync_session() as db:
        project = db.scalar(select(Project).where(Project.id == pid))
        if project is None:
            return
        storage = get_storage()
        storage.delete_prefix(f"u/{project.user_id}/p/{pid}/")
        for job_id in db.scalars(select(TrainingJob.id).where(TrainingJob.project_id == pid)):
            storage.delete_prefix(f"j/{job_id}/")
        db.execute(delete(Project).where(Project.id == pid))
        db.commit()
    events.publish(pid, "deleted", {})
    log.info("project_purged", project_id=project_id)


@app.task(name="doctune.workers.tasks.housekeeping.purge_user", max_retries=5, default_retry_delay=60)
def purge_user(user_id: str) -> None:
    """Account deletion: every project (files first), then the user row (keys cascade), then Supabase auth."""
    uid = uuid.UUID(user_id)
    with sync_session() as db:
        project_ids = list(db.scalars(select(Project.id).where(Project.user_id == uid)))
    for pid in project_ids:
        purge_project(str(pid))
    get_storage().delete_prefix(f"u/{uid}/")
    with sync_session() as db:
        db.execute(delete(User).where(User.id == uid))
        db.commit()
    delete_supabase_user(uid)
    log.info("user_purged", user_id=user_id, projects=len(project_ids))


def delete_supabase_user(uid: uuid.UUID) -> None:
    settings = get_settings()
    if settings.supabase_service_role_key is None:
        log.warning("supabase_user_not_deleted", reason="SUPABASE_SERVICE_ROLE_KEY not set", user_id=str(uid))
        return
    key = settings.supabase_service_role_key.get_secret_value()
    r = httpx.delete(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{uid}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=15,
    )
    if r.status_code not in (200, 204, 404):
        r.raise_for_status()
