import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from doctune.models.enums import DocumentStatus
from doctune.schemas.common import SignedUrlOut


class DocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    page_count: int | None
    ocr_pages: int
    error: str | None
    created_at: datetime


class DocumentWithChunks(DocumentOut):
    chunk_count: int = 0


class DocumentUploadOut(BaseModel):
    document: DocumentOut
    upload: SignedUrlOut


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    ordinal: int
    section_path: str
    text: str
    token_count: int
    page_start: int | None
    page_end: int | None
