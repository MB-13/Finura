"""Document upload flow: create record + signed upload URL, verify the upload, remove."""

import re
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.config import get_settings
from doctune.core.errors import AppError, Conflict, LimitExceeded, NotFound
from doctune.core.storage import SignedUrl, Storage
from doctune.models.document import Chunk, Document
from doctune.models.enums import DocumentStatus, ProjectStatus
from doctune.models.project import Project
from doctune.parsing.extract import CONTENT_TYPES, kind_for_filename, sniff
from doctune.services import projects as project_service
from doctune.services.transitions import Actor

UPLOAD_STATUSES = {ProjectStatus.draft, ProjectStatus.uploaded, ProjectStatus.awaiting_style}
SNIFF_BYTES = 8192


class UnsupportedFileType(AppError):
    status_code, code, message = (
        415,
        "unsupported_file_type",
        "Upload a PDF, Word (.docx), text or Markdown file.",
    )


def storage_key(user_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    return f"u/{user_id}/p/{project_id}/docs/{document_id}/{safe_filename(filename)}"


def safe_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "document"
    return f"{stem[:100]}{suffix}"


async def _committed_bytes(db: AsyncSession, project_id: uuid.UUID) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
            Document.project_id == project_id, Document.status != DocumentStatus.failed
        )
    )
    return int(total or 0)


async def create_upload(
    db: AsyncSession, storage: Storage, project: Project, filename: str, size_bytes: int
) -> tuple[Document, SignedUrl]:
    settings = get_settings()
    if project.status not in UPLOAD_STATUSES:
        raise Conflict("Documents can't be added at this stage.", code="invalid_state")
    kind = kind_for_filename(filename)
    if kind is None:
        raise UnsupportedFileType()
    max_file = settings.max_file_mb * 1024 * 1024
    if size_bytes > max_file:
        raise LimitExceeded(f"Files can be up to {settings.max_file_mb} MB.")
    if await _committed_bytes(db, project.id) + size_bytes > settings.max_project_mb * 1024 * 1024:
        raise LimitExceeded(f"A project can hold up to {settings.max_project_mb} MB of documents.")

    doc_id = uuid.uuid4()
    content_type = CONTENT_TYPES[kind]
    doc = Document(
        id=doc_id,
        project_id=project.id,
        filename=safe_filename(filename),
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key(project.user_id, project.id, doc_id, filename),
        status=DocumentStatus.pending_upload,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    url = storage.presign_put(doc.storage_key, content_type=content_type, max_bytes=size_bytes)
    return doc, url


async def get_doc(db: AsyncSession, project: Project, document_id: uuid.UUID) -> Document:
    doc = await db.scalar(select(Document).where(Document.id == document_id, Document.project_id == project.id))
    if doc is None:
        raise NotFound("Document not found")
    return doc


async def complete_upload(db: AsyncSession, storage: Storage, project: Project, doc: Document) -> Document:
    if doc.status != DocumentStatus.pending_upload:
        return doc  # idempotent: completing twice is fine
    info = storage.head(doc.storage_key)
    if info is None:
        raise Conflict("The file hasn't been uploaded yet.", code="upload_missing")
    kind = kind_for_filename(doc.filename)
    if info.size != doc.size_bytes or kind is None or not sniff(storage.read_bytes(doc.storage_key, SNIFF_BYTES), kind):
        storage.delete(doc.storage_key)
        await db.delete(doc)
        await db.commit()
        raise UnsupportedFileType("The uploaded file doesn't match its name or size. Please upload it again.")

    doc.status = DocumentStatus.uploaded
    project.total_bytes = await _committed_bytes(db, project.id)
    if project.status in (ProjectStatus.draft, ProjectStatus.awaiting_style):
        await project_service.transition(db, project, ProjectStatus.uploaded, actor=Actor.api)
    else:
        await db.commit()
    await db.refresh(doc)
    return doc


async def remove(db: AsyncSession, storage: Storage, project: Project, doc: Document) -> None:
    if project.status not in UPLOAD_STATUSES:
        raise Conflict("Documents can't be removed at this stage.", code="invalid_state")
    await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    await db.delete(doc)
    await db.flush()
    storage.delete(doc.storage_key)
    project.total_bytes = await _committed_bytes(db, project.id)
    remaining = await db.scalar(select(func.count()).select_from(Document).where(Document.project_id == project.id))
    if not remaining and project.status == ProjectStatus.uploaded:
        await project_service.transition(db, project, ProjectStatus.draft, actor=Actor.api)
    elif not remaining and project.status == ProjectStatus.awaiting_style:
        await project_service.transition(db, project, ProjectStatus.uploaded, actor=Actor.api, commit=False)
        await project_service.transition(db, project, ProjectStatus.draft, actor=Actor.api)
    else:
        await db.commit()


async def documents_to_parse(db: AsyncSession, project_id: uuid.UUID) -> list[Document]:
    rows = await db.execute(
        select(Document).where(Document.project_id == project_id, Document.status == DocumentStatus.uploaded)
    )
    return list(rows.scalars())
