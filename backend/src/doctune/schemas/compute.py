from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ComputeStatusName = Literal["unchecked", "ok", "invalid", "no_gpu_quota"]


class KaggleAccountPut(BaseModel):
    username: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    api_token: str = Field(min_length=10, max_length=300)

    @field_validator("username", "api_token", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class KaggleAccountOut(BaseModel):
    username: str
    token_hint: str  # e.g. "...ab12"; the token itself is never returned
    status: ComputeStatusName
    status_message: str | None
    gpu_hours_used: float | None
    gpu_hours_total: float | None
    quota_refresh_at: datetime | None
    checked_at: datetime | None
