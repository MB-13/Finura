from typing import Literal

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class SignedUrlOut(BaseModel):
    url: str
    method: Literal["PUT", "GET"]
    headers: dict[str, str]
    expires_at: int
