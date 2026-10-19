"""Chat with your fine-tuned model: llama.cpp (base GGUF + LoRA GGUF) plus RAG over your documents."""

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from doctune.core.config import get_settings
from doctune.core.errors import AppError, Conflict, RateLimited
from doctune.inference import manager, rag
from doctune.models.enums import ProjectStatus
from doctune.models.generation import DatasetVersion
from doctune.models.project import Project
from doctune.models.training import Artifact, ArtifactKind, TrainingJob
from doctune.routers.deps import DB, OwnedProject
from doctune.training.catalog import BY_ID

router = APIRouter(prefix="/projects/{project_id}/playground", tags=["playground"])

MESSAGES_PER_MINUTE = 20
# adapter -> GGUF conversion is capped at ~21 min; past this it failed or never ran
CONVERT_GRACE = timedelta(minutes=30)
# tests install a transport here (a fake llama-server)
test_transport: httpx.AsyncBaseTransport | None = None


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatIn(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)
    use_rag: bool = True
    compare_base: bool = False
    temperature: float = Field(default=0.7, ge=0, le=1.5)
    max_tokens: int = Field(default=384, ge=16, le=512)


UnavailableReason = Literal["no_model", "too_large", "not_ready", "preparing", "prepare_failed"]


class PlaygroundStatus(BaseModel):
    available: bool
    reason: str | None = None
    # why it's unavailable, so the UI can tell "wait a minute" from "this will never open here"
    reason_code: UnavailableReason | None = None
    state: Literal["cold", "warming", "warm"] = "cold"
    source: Literal["final", "checkpoint"] | None = None
    checkpoint_step: int | None = None
    model: str | None = None


class Unavailable(AppError):
    status_code, code = 409, "playground_unavailable"

    def __init__(self, message: str, reason: UnavailableReason) -> None:
        super().__init__(message, details={"reason": reason})
        self.reason: UnavailableReason = reason


async def _target(db: AsyncSession, project: Project) -> tuple[TrainingJob, Artifact, Literal["final", "checkpoint"]]:
    job = await db.scalar(
        select(TrainingJob).where(TrainingJob.project_id == project.id).order_by(TrainingJob.created_at.desc()).limit(1)
    )
    if job is None:
        raise Unavailable("Train a model first.", "no_model")
    model = BY_ID.get(job.base_model_id)
    limit = get_settings().playground_max_params_b
    if model is None or model.playground_gguf is None or model.params_b > limit:
        name = model.display_name if model else job.base_model_id
        raise Unavailable(
            f"{name} is bigger than this server can run for chat (it runs models up to {limit:g}B). Your model is "
            "fine: download it and chat with it on your own computer with Ollama, or train a 4B model to use "
            "the playground.",
            "too_large",
        )
    if project.status == ProjectStatus.ready:
        kind, source = ArtifactKind.adapter_gguf, "final"
    elif project.status == ProjectStatus.paused:
        kind, source = ArtifactKind.checkpoint_gguf, "checkpoint"
    else:
        raise Unavailable("The playground opens when training is paused or finished.", "not_ready")
    art = await db.scalar(select(Artifact).where(Artifact.job_id == job.id, Artifact.kind == kind, Artifact.uploaded))
    if art is None:
        if source == "final" and job.ended_at and datetime.now(UTC) - job.ended_at > CONVERT_GRACE:
            raise Unavailable(
                "We couldn't prepare your model for the playground. Your model is fine: download it and "
                "run it with Ollama.",
                "prepare_failed",
            )
        raise Unavailable("Your model is still being prepared for the playground. Try again in a minute.", "preparing")
    return job, art, source  # type: ignore[return-value]


@router.get("/status")
async def playground_status(project: OwnedProject, db: DB) -> PlaygroundStatus:
    try:
        job, art, source = await _target(db, project)
    except Unavailable as exc:
        return PlaygroundStatus(available=False, reason=exc.message, reason_code=exc.reason)
    key = manager.server_key(job.id, source)
    state = manager.current()
    warm = "warm" if state and state.key == key else "warming" if manager.is_loading(key) else "cold"
    return PlaygroundStatus(
        available=True,
        state=warm,
        source=source,
        model=job.base_model_id,
        checkpoint_step=(art.meta or {}).get("step") if source == "checkpoint" else None,
    )


@router.post("/warmup", status_code=status.HTTP_202_ACCEPTED)
async def warmup(project: OwnedProject, db: DB) -> PlaygroundStatus:
    from doctune.workers.tasks.inference import ensure_loaded

    job, art, source = await _target(db, project)
    key = manager.server_key(job.id, source)
    state = manager.current()
    if not (state and state.key == key) and not manager.is_loading(key):
        repo, filename = BY_ID[job.base_model_id].playground_gguf  # type: ignore[misc]
        ensure_loaded.delay(key, repo, filename, art.storage_key)
    return await playground_status(project, db)


async def _limits(user_id: str) -> None:
    r = aioredis.Redis.from_url(get_settings().redis_url)
    async with r:
        minute = int(time.time() // 60)
        count = await r.incr(f"pg:rate:{user_id}:{minute}")
        await r.expire(f"pg:rate:{user_id}:{minute}", 120)
        if count > MESSAGES_PER_MINUTE:
            raise RateLimited("You're sending messages too quickly. Wait a moment.")
        if not await r.set(f"pg:busy:{user_id}", "1", nx=True, ex=180):
            raise RateLimited("Wait for the current answer to finish.")


async def _release(user_id: str) -> None:
    r = aioredis.Redis.from_url(get_settings().redis_url)
    async with r:
        await r.delete(f"pg:busy:{user_id}")


async def _stream(
    url: str, payload: dict[str, Any], sources: list[dict[str, Any]], user_id: str
) -> AsyncIterator[dict[str, str]]:
    usage: dict[str, Any] = {}
    try:
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(180, connect=5), transport=test_transport) as client,
            client.stream("POST", f"{url}/v1/chat/completions", json=payload) as resp,
        ):
            if resp.status_code != 200:
                yield {"event": "error", "data": json.dumps({"message": "The model server returned an error."})}
                return
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        yield {"event": "token", "data": json.dumps({"text": text})}
        if sources:
            yield {"event": "sources", "data": json.dumps(sources, default=str)}
        yield {"event": "done", "data": json.dumps({"usage": usage})}
        manager.touch()
    except httpx.HTTPError:
        yield {"event": "error", "data": json.dumps({"message": "Lost connection to the model server."})}
    finally:
        await _release(user_id)


@router.post(
    "/chat",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "token / sources / done / error"}},
)
async def chat(body: ChatIn, project: OwnedProject, db: DB) -> EventSourceResponse:
    job, _art, source = await _target(db, project)
    key = manager.server_key(job.id, source)
    state = manager.current()
    if not (state and state.key == key):
        raise Conflict("Your model is loading. Call warmup and try again shortly.", code="warming_up")
    await _limits(str(project.user_id))

    version = await db.get(DatasetVersion, project.dataset_version_id) if project.dataset_version_id else None
    question = next(m.content for m in reversed(body.messages) if m.role == "user")
    hits = await rag.retrieve(db, project.id, question) if body.use_rag else []
    system = rag.system_prompt(version.system_prompt if version else None, [text for _, text in hits])
    messages = ([{"role": "system", "content": system}] if system else []) + [
        m.model_dump() for m in body.messages[-12:]
    ]
    payload: dict[str, Any] = {
        "messages": messages,
        "stream": True,
        "temperature": body.temperature,
        "max_tokens": body.max_tokens,
        # Qwen3/3.5 were fine-tuned in non-thinking mode
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if body.compare_base:
        payload["lora"] = [{"id": 0, "scale": 0.0}]  # same server, adapter switched off for this request
    sources = [{"chunk_id": s.chunk_id, "section_path": s.section_path, "excerpt": s.excerpt} for s, _ in hits]
    return EventSourceResponse(_stream(state.url, payload, sources, str(project.user_id)), ping=15)
