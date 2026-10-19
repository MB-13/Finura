"""Admin-only free-tier usage view (docs/plan/08 §8)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.auth import CurrentUserDep
from doctune.core.config import get_settings
from doctune.core.db import get_session
from doctune.core.errors import NotFound
from doctune.core.storage import LocalStorage, get_storage
from doctune.models.generation import GenerationRun, GenState
from doctune.models.project import Project
from doctune.models.training import JobState, TrainingJob
from doctune.models.user import EmailLog, User
from doctune.workers.celery_app import QUEUES

router = APIRouter(prefix="/admin", tags=["admin"], include_in_schema=False)
DB = Annotated[AsyncSession, Depends(get_session)]


class Usage(BaseModel):
    db_bytes: int
    db_limit_bytes: int
    storage_bytes: int
    storage_limit_bytes: int
    users: int
    projects: int
    active_jobs: int
    active_runs: int
    queue_depths: dict[str, int]
    emails_today: int


@router.get("/usage")
async def usage(user: CurrentUserDep, db: DB) -> Usage:
    me = await db.get(User, user.id)
    if me is None or not me.is_admin:
        raise NotFound()
    storage = get_storage()
    storage_bytes = (
        sum(p.stat().st_size for p in storage.root.rglob("*") if p.is_file())
        if isinstance(storage, LocalStorage)
        else 0
    )
    client = Redis.from_url(get_settings().redis_url)
    async with client:
        depths = {q: int(await client.llen(q)) for q in QUEUES}
    since = datetime.now(UTC) - timedelta(days=1)
    return Usage(
        db_bytes=int(await db.scalar(text("select pg_database_size(current_database())")) or 0),
        db_limit_bytes=500 * 1024**2,
        storage_bytes=storage_bytes,
        storage_limit_bytes=10 * 1024**3,
        users=await db.scalar(select(func.count()).select_from(User)) or 0,
        projects=await db.scalar(select(func.count()).select_from(Project).where(Project.deleted_at.is_(None))) or 0,
        active_jobs=await db.scalar(
            select(func.count())
            .select_from(TrainingJob)
            .where(TrainingJob.state.in_([JobState.running, JobState.paused]))
        )
        or 0,
        active_runs=await db.scalar(
            select(func.count())
            .select_from(GenerationRun)
            .where(GenerationRun.state.in_([GenState.running, GenState.waiting_quota, GenState.finalizing]))
        )
        or 0,
        queue_depths=depths,
        emails_today=await db.scalar(select(func.count()).select_from(EmailLog).where(EmailLog.sent_at >= since)) or 0,
    )
