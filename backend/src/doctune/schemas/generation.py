import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doctune.models.generation import GenKind, GenState, PairOrigin, PairSplit
from doctune.services.formats import DatasetFormat, PairRecord
from doctune.services.style import StyleIn, Warning


class StyleOut(StyleIn):
    id: uuid.UUID
    created_at: datetime
    warnings: list[Warning] = Field(default_factory=list)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: GenKind
    state: GenState
    style_id: uuid.UUID
    pairs_per_chunk: int
    target_pairs: int
    total_chunks: int
    done_chunks: int
    pairs_generated: int
    pairs_kept: int
    tokens_in: int
    tokens_out: int
    resume_at: datetime | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class PreviewIn(BaseModel):
    n_chunks: int = Field(default=4, ge=1, le=6)
    pairs_per_chunk: int = Field(default=2, ge=1, le=3)


class GenerateIn(BaseModel):
    confirm: Literal[True]


class ChunkRef(BaseModel):
    id: uuid.UUID
    section_path: str
    excerpt: str


class PairOut(BaseModel):
    id: uuid.UUID
    dataset_format: DatasetFormat
    # the first prompt and the last response, whatever the format (search and the table use these)
    question: str
    answer: str
    # the whole example in its format's shape
    record: PairRecord
    split: PairSplit
    origin: PairOrigin
    judge_correctness: int | None
    judge_style: int | None
    judge_reason: str | None
    kept: bool | None
    dropped_reason: str | None
    edited: bool
    chunk: ChunkRef | None


class PairPatch(BaseModel):
    question: str | None = Field(default=None, min_length=3, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    # replaces the whole example; must be in the pair's format
    record: PairRecord | None = None
    kept: bool | None = None
    split: Literal["train", "eval"] | None = None


class PairCreate(BaseModel):
    """Either `record` (in the project's dataset format) or `question` + `answer`."""

    question: str | None = Field(default=None, min_length=3, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    record: PairRecord | None = None
    split: Literal["train", "eval"] = "train"

    @model_validator(mode="after")
    def _has_content(self) -> "PairCreate":
        if self.record is None and (self.question is None or self.answer is None):
            raise ValueError("Send a record, or a question and an answer")
        return self


class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=2000)
    action: Literal["drop", "restore", "move_to_train", "move_to_eval"]


class BulkOut(BaseModel):
    updated: int


class ResumeInfo(BaseModel):
    run_id: uuid.UUID
    remaining_chunks: int
    total_chunks: int


class MoreInfo(BaseModel):
    """What one "generate more" pass would do: another round over the documents, added to the current pairs."""

    target_pairs: int
    sections: int
    pairs_to_generate: int


class DatasetStats(BaseModel):
    kept: int
    train: int
    eval: int
    dropped_by_reason: dict[str, int]
    avg_correctness: float | None
    avg_style: float | None
    answer_words: dict[str, int]
    # approval rules, so the UI can show what's missing before the user clicks Approve
    min_pairs: int
    small_min_pairs: int  # fewest pairs the user may approve on purpose (approve with allow_small)
    max_pairs: int
    min_eval: int
    # set when the last generation was finished early and can pick up the sections it skipped
    resume: ResumeInfo | None = None
    # set when the dataset is below the project's target and the documents can be mined for more pairs
    more: MoreInfo | None = None


class ApproveIn(BaseModel):
    # approve a dataset smaller than min_pairs (but at least small_min_pairs) knowingly
    allow_small: bool = False


class DatasetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    train_count: int
    eval_count: int
    sha256_train: str
    sha256_eval: str
    dataset_format: DatasetFormat
    approved_at: datetime


class Estimate(BaseModel):
    chunks: int
    pairs_per_chunk: int
    supported_pairs: int
    target_pairs: int
    est_requests: int
    est_tokens: int
    est_minutes: float
    est_days: float
    providers: list[str]
    fits_daily_quota: bool


class ExportIn(BaseModel):
    # training: exactly what the model trains on (chat messages); native: the format's own layout
    # (Alpaca for instructions, ShareGPT for conversations)
    shape: Literal["training", "native"] = "training"


class ExportOut(BaseModel):
    url: str
    expires_at: int
