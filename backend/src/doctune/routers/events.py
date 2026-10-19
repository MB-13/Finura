import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from redis.asyncio import Redis
from sse_starlette import EventSourceResponse

from doctune.core.config import get_settings
from doctune.core.events import channel
from doctune.routers.deps import DB, OwnedProject
from doctune.services.views import project_out

router = APIRouter(prefix="/projects/{project_id}", tags=["events"])


async def _stream(request: Request, project_id: str, snapshot: dict[str, Any]) -> AsyncIterator[dict[str, str]]:
    yield {"event": "snapshot", "data": json.dumps(snapshot, default=str)}
    client = Redis.from_url(get_settings().redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(project_id))
    try:
        while not await request.is_disconnected():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            if message is None:
                continue
            payload = json.loads(message["data"])
            yield {"event": payload["type"], "data": json.dumps(payload["data"], default=str)}
            if payload["type"] == "deleted":
                break
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await client.aclose()


@router.get(
    "/events",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"}},
)
async def project_events(request: Request, project: OwnedProject, db: DB) -> EventSourceResponse:
    """Live updates: `snapshot` first, then `status`, `progress`, `train_metrics`, `notice`, `deleted`."""
    snapshot = (await project_out(db, project)).model_dump(mode="json")
    return EventSourceResponse(
        _stream(request, str(project.id), snapshot),
        ping=15,
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
