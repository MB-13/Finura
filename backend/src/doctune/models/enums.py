from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class ProjectStatus(StrEnum):
    draft = "draft"
    uploaded = "uploaded"
    parsing = "parsing"
    awaiting_style = "awaiting_style"
    previewing = "previewing"
    generating = "generating"
    in_review = "in_review"
    awaiting_run = "awaiting_run"
    training = "training"
    paused = "paused"
    evaluating = "evaluating"
    ready = "ready"
    failed = "failed"


class DocumentStatus(StrEnum):
    pending_upload = "pending_upload"
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Native Postgres enum stored by value."""
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=True)
