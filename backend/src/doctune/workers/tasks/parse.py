import uuid

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from doctune.core import events
from doctune.core.db import sync_session
from doctune.core.storage import get_storage
from doctune.models.document import Chunk, Document
from doctune.models.enums import DocumentStatus, ProjectStatus
from doctune.models.project import Project
from doctune.parsing.chunker import chunk_pages
from doctune.parsing.extract import ParseError, extract, kind_for_filename
from doctune.services.projects import transition_sync
from doctune.services.transitions import Actor
from doctune.workers.celery_app import app

log = structlog.get_logger()

NO_TEXT_MESSAGE = "We couldn't read any text from your documents. Remove them and upload different files."


@app.task(name="doctune.workers.tasks.parse.parse_document", soft_time_limit=300, time_limit=360, max_retries=2)
def parse_document(document_id: str) -> None:
    doc_id = uuid.UUID(document_id)
    with sync_session() as db:
        doc = db.get(Document, doc_id)
        if doc is None or doc.status in (DocumentStatus.parsed, DocumentStatus.failed):
            return  # gone, or already handled (idempotent on retry/duplicate delivery)
        project_id = doc.project_id
        doc.status = DocumentStatus.parsing
        db.commit()
        events.publish(project_id, "progress", {"phase": "parse", "document_id": document_id, "state": "parsing"})

        try:
            kind = kind_for_filename(doc.filename)
            if kind is None:
                raise ParseError("Unsupported file type.")
            data = get_storage().read_bytes(doc.storage_key)
            extracted = extract(data, kind)
            chunks = chunk_pages(extracted.pages)
            if not chunks:
                raise ParseError("No readable text found in this file.")
        except ParseError as exc:
            _fail(db, doc, str(exc))
        except SoftTimeLimitExceeded:
            _fail(db, doc, "This file took too long to process. Try splitting it into smaller files.")
        except Exception:
            log.exception("parse_failed", document_id=document_id)
            _fail(db, doc, "Something went wrong while reading this file.")
        else:
            db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            db.add_all(
                Chunk(
                    project_id=project_id,
                    document_id=doc.id,
                    ordinal=i,
                    section_path=c.section_path,
                    text=c.text,
                    token_count=c.token_count,
                    page_start=c.page_start,
                    page_end=c.page_end,
                )
                for i, c in enumerate(chunks)
            )
            doc.status = DocumentStatus.parsed
            doc.page_count = extracted.page_count
            doc.ocr_pages = extracted.ocr_pages
            doc.error = None
            db.commit()
            log.info("document_parsed", document_id=document_id, chunks=len(chunks), ocr_pages=extracted.ocr_pages)
            events.publish(
                project_id,
                "progress",
                {"phase": "parse", "document_id": document_id, "state": "parsed", "chunks": len(chunks)},
            )
            from doctune.workers.tasks.embed import embed_chunks

            embed_chunks.delay(document_id)

        finish_parsing_if_done(project_id)


def _fail(db: Session, doc: Document, message: str) -> None:
    db.rollback()
    doc.status = DocumentStatus.failed
    doc.error = message
    db.commit()
    events.publish(doc.project_id, "progress", {"phase": "parse", "document_id": str(doc.id), "state": "failed"})


def finish_parsing_if_done(project_id: uuid.UUID) -> None:
    """Move the project on once every document is parsed or failed.

    The project row is locked for the whole check-and-transition, so when several documents
    finish at the same moment exactly one of them moves the project.
    """
    with sync_session() as db:
        project = db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
        if project is None or project.status != ProjectStatus.parsing:
            db.rollback()
            return
        pending = db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.project_id == project_id,
                Document.status.in_([DocumentStatus.uploaded, DocumentStatus.parsing]),
            )
        )
        if pending:
            db.rollback()
            return
        chunk_count = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.project_id == project_id)) or 0
        if chunk_count:
            transition_sync(db, project_id, ProjectStatus.awaiting_style, actor=Actor.worker)
        else:
            transition_sync(
                db,
                project_id,
                ProjectStatus.failed,
                actor=Actor.worker,
                reason="no_text",
                message=NO_TEXT_MESSAGE,
                retry_to=ProjectStatus.uploaded,
            )
