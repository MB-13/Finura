from typing import Literal

from pydantic import BaseModel


class Limits(BaseModel):
    file_mb: int
    project_mb: int
    max_pairs: int


class MetaOut(BaseModel):
    version: str
    notebook_url: str
    notebook_version: str
    limits: Limits
    providers: list[str]


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadyOut(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    redis: bool
