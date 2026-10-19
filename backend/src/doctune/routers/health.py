from typing import Annotated

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.config import Settings, get_settings
from doctune.core.db import get_session
from doctune.schemas.meta import HealthOut, Limits, MetaOut, ReadyOut

router = APIRouter(tags=["meta"])


@router.get("/healthz")
async def healthz() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/readyz", responses={503: {"model": ReadyOut}})
async def readyz(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyOut:
    db_ok = redis_ok = False
    try:
        await session.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: S110 - readiness reports, never raises
        pass
    try:
        client = Redis.from_url(settings.redis_url)
        async with client:
            redis_ok = bool(await client.ping())
    except Exception:  # noqa: S110
        pass
    ok = db_ok and redis_ok
    if not ok:
        response.status_code = 503
    return ReadyOut(status="ok" if ok else "degraded", database=db_ok, redis=redis_ok)


@router.get("/meta")
async def meta(settings: Annotated[Settings, Depends(get_settings)]) -> MetaOut:
    return MetaOut(
        version=settings.app_version,
        notebook_url=settings.notebook_url,
        notebook_version=settings.notebook_version,
        limits=Limits(file_mb=settings.max_file_mb, project_mb=settings.max_project_mb, max_pairs=settings.max_pairs),
        providers=["groq", "gemini", "cerebras"],
    )
