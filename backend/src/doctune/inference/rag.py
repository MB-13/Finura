"""Retrieval over the project's own chunks (pgvector) to ground playground answers in facts."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from doctune.embeddings.encoder import get_encoder
from doctune.models.document import Chunk
from doctune.parsing.chunker import count_tokens

TOP_K = 4
MAX_DISTANCE = 0.6
CONTEXT_TOKENS = 1500

RAG_INSTRUCTIONS = (
    "Use the numbered context below when it is relevant. If the context doesn't contain the answer, say you "
    "don't know rather than guessing."
)


@dataclass
class Source:
    chunk_id: uuid.UUID
    section_path: str
    excerpt: str
    distance: float


async def retrieve(db: AsyncSession, project_id: uuid.UUID, query: str) -> list[tuple[Source, str]]:
    vector = await run_in_threadpool(get_encoder().query, query)
    distance = Chunk.embedding.cosine_distance(vector)
    rows = (
        await db.execute(
            select(Chunk.id, Chunk.section_path, Chunk.text, distance.label("d"))
            .where(Chunk.project_id == project_id, Chunk.embedding.is_not(None))
            .order_by(distance)
            .limit(TOP_K)
        )
    ).all()
    out: list[tuple[Source, str]] = []
    budget = CONTEXT_TOKENS
    for cid, path, text, d in rows:
        if d > MAX_DISTANCE:
            continue
        tokens = count_tokens(text)
        if tokens > budget:
            break
        budget -= tokens
        out.append((Source(cid, path, text[:300], round(float(d), 3)), text))
    return out


def system_prompt(base: str | None, contexts: list[str]) -> str:
    parts = [base] if base else []
    if contexts:
        numbered = "\n\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
        parts.append(f"{RAG_INSTRUCTIONS}\n\nCONTEXT:\n{numbered}")
    return "\n\n".join(parts)
