import uuid

import structlog
from sqlalchemy import select

from doctune.core.db import sync_session
from doctune.embeddings.encoder import get_encoder
from doctune.models.document import Chunk
from doctune.workers.celery_app import app

log = structlog.get_logger()
BATCH = 32


@app.task(name="doctune.workers.tasks.embed.embed_chunks", soft_time_limit=600, time_limit=660)
def embed_chunks(document_id: str) -> int:
    """Embed this document's chunks for RAG. Idempotent: only chunks without an embedding."""
    encoder = get_encoder()
    done = 0
    with sync_session() as db:
        while True:
            rows = list(
                db.execute(
                    select(Chunk)
                    .where(Chunk.document_id == uuid.UUID(document_id), Chunk.embedding.is_(None))
                    .order_by(Chunk.ordinal)
                    .limit(BATCH)
                ).scalars()
            )
            if not rows:
                break
            for chunk, vector in zip(rows, encoder.passages([c.text for c in rows]), strict=True):
                chunk.embedding = vector
            db.commit()
            done += len(rows)
    return done
