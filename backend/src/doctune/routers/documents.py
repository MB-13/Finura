import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from doctune.core.ratelimit import limit
from doctune.models.document import Chunk, Document
from doctune.routers.deps import DB, LockedProject, OwnedProject, StorageDep
from doctune.schemas.common import Page, SignedUrlOut
from doctune.schemas.documents import (
    ChunkOut,
    DocumentCreate,
    DocumentOut,
    DocumentUploadOut,
    DocumentWithChunks,
)
from doctune.services import documents as document_service

router = APIRouter(prefix="/projects/{project_id}", tags=["documents"])


@router.post("/documents", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit("upload", 60))])
async def create_document(
    body: DocumentCreate, project: LockedProject, db: DB, storage: StorageDep
) -> DocumentUploadOut:
    """Register a document and get a signed URL to PUT the file to."""
    doc, url = await document_service.create_upload(db, storage, project, body.filename, body.size_bytes)
    return DocumentUploadOut(
        document=DocumentOut.model_validate(doc),
        upload=SignedUrlOut(url=url.url, method=url.method, headers=url.headers, expires_at=url.expires_at),
    )


@router.post("/documents/{document_id}/complete")
async def complete_document(document_id: uuid.UUID, project: LockedProject, db: DB, storage: StorageDep) -> DocumentOut:
    """Call after the PUT succeeds: verifies size and real file type."""
    doc = await document_service.get_doc(db, project, document_id)
    doc = await document_service.complete_upload(db, storage, project, doc)
    return DocumentOut.model_validate(doc)


@router.get("/documents")
async def list_documents(project: OwnedProject, db: DB) -> list[DocumentWithChunks]:
    chunk_counts = select(Chunk.document_id, func.count().label("n")).group_by(Chunk.document_id).subquery()
    rows = await db.execute(
        select(Document, func.coalesce(chunk_counts.c.n, 0))
        .outerjoin(chunk_counts, chunk_counts.c.document_id == Document.id)
        .where(Document.project_id == project.id)
        .order_by(Document.created_at)
    )
    return [DocumentWithChunks.model_validate(doc).model_copy(update={"chunk_count": n}) for doc, n in rows.all()]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, project: LockedProject, db: DB, storage: StorageDep) -> None:
    doc = await document_service.get_doc(db, project, document_id)
    await document_service.remove(db, storage, project, doc)


@router.get("/chunks")
async def list_chunks(
    project: OwnedProject,
    db: DB,
    document_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(pattern=r"^\d+$", description="opaque cursor from `next_cursor`")] = None,
) -> Page[ChunkOut]:
    offset = int(cursor or 0)
    stmt = select(Chunk).where(Chunk.project_id == project.id)
    if document_id:
        stmt = stmt.where(Chunk.document_id == document_id)
    if q:
        stmt = stmt.where(Chunk.text.ilike(f"%{q.replace('%', r'\%').replace('_', r'\_')}%", escape="\\"))
    stmt = stmt.order_by(Chunk.document_id, Chunk.ordinal).offset(offset).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars())
    return Page(
        items=[ChunkOut.model_validate(c) for c in rows[:limit]],
        next_cursor=str(offset + limit) if len(rows) > limit else None,
    )
