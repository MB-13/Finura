import uuid

from pydantic import BaseModel, ConfigDict, Field


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    display_name: str | None
    onboarding_done: bool
    email_notifications: bool


class MePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    onboarding_done: bool | None = None
    email_notifications: bool | None = None
