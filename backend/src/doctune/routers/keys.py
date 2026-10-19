from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doctune.core.auth import CurrentUserDep
from doctune.core.crypto import encrypt, mask
from doctune.core.db import get_session
from doctune.core.errors import Conflict, NotFound
from doctune.core.ratelimit import limit
from doctune.llm.providers import PROVIDERS
from doctune.models.generation import KeyStatus, Provider, ProviderKey

router = APIRouter(tags=["keys"])
DB = Annotated[AsyncSession, Depends(get_session)]


class ModelOut(BaseModel):
    id: str
    license: str | None
    rpm: int
    tpd: int | None


class ProviderOut(BaseModel):
    provider: Provider
    name: str
    models: list[ModelOut]
    requires_terms_ack: bool
    note: str | None
    key_help_url: str


class ProviderKeyOut(BaseModel):
    provider: Provider
    last4: str
    status: KeyStatus
    priority: int
    default_model: str | None
    terms_acknowledged: bool
    last_verified_at: datetime | None
    quota_reset_at: datetime | None


class KeyPut(BaseModel):
    api_key: str = Field(min_length=10, max_length=300)
    default_model: str | None = Field(default=None, max_length=200)
    terms_acknowledged: bool = False


class KeyPatch(BaseModel):
    priority: int | None = Field(default=None, ge=0, le=10)
    default_model: str | None = Field(default=None, max_length=200)


def _out(k: ProviderKey) -> ProviderKeyOut:
    return ProviderKeyOut(
        provider=k.provider,
        last4=k.last4,
        status=k.status,
        priority=k.priority,
        default_model=k.default_model,
        terms_acknowledged=k.terms_acknowledged_at is not None,
        last_verified_at=k.last_verified_at,
        quota_reset_at=k.quota_reset_at,
    )


async def _get(db: AsyncSession, user_id: object, provider: Provider) -> ProviderKey:
    key = await db.scalar(select(ProviderKey).where(ProviderKey.user_id == user_id, ProviderKey.provider == provider))
    if key is None:
        raise NotFound("No key saved for this provider")
    return key


@router.get("/providers")
async def list_providers(_: CurrentUserDep) -> list[ProviderOut]:
    return [
        ProviderOut(
            provider=p.provider,
            name=p.name,
            models=[ModelOut(id=m.id, license=m.license, rpm=m.rpm, tpd=m.tpd) for m in p.models],
            requires_terms_ack=p.requires_terms_ack,
            note=p.note,
            key_help_url=p.key_help_url,
        )
        for p in PROVIDERS.values()
    ]


@router.get("/keys")
async def list_keys(user: CurrentUserDep, db: DB) -> list[ProviderKeyOut]:
    rows = await db.scalars(
        select(ProviderKey).where(ProviderKey.user_id == user.id).order_by(ProviderKey.priority, ProviderKey.created_at)
    )
    return [_out(k) for k in rows]


@router.put("/keys/{provider}", dependencies=[Depends(limit("put_key", 10))])
async def put_key(provider: Provider, body: KeyPut, user: CurrentUserDep, db: DB) -> ProviderKeyOut:
    from doctune.workers.tasks.keys import verify_key

    spec = PROVIDERS[provider]
    if spec.requires_terms_ack and not body.terms_acknowledged:
        raise Conflict(f"Please accept {spec.name}'s terms to use this provider.", code="terms_required")
    secret = body.api_key.strip()
    key = await db.scalar(select(ProviderKey).where(ProviderKey.user_id == user.id, ProviderKey.provider == provider))
    if key is None:
        count = len((await db.scalars(select(ProviderKey.id).where(ProviderKey.user_id == user.id))).all())
        key = ProviderKey(user_id=user.id, provider=provider, priority=count)
        db.add(key)
    key.ciphertext = encrypt(secret)
    key.last4 = mask(secret)
    key.status = KeyStatus.unverified
    key.quota_reset_at = None
    key.default_model = body.default_model
    key.terms_acknowledged_at = datetime.now(UTC) if body.terms_acknowledged else None
    await db.commit()
    await db.refresh(key)
    verify_key.delay(str(user.id), provider.value)
    return _out(key)


@router.patch("/keys/{provider}")
async def patch_key(provider: Provider, body: KeyPatch, user: CurrentUserDep, db: DB) -> ProviderKeyOut:
    key = await _get(db, user.id, provider)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(key, field, value)
    await db.commit()
    await db.refresh(key)
    return _out(key)


@router.delete("/keys/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(provider: Provider, user: CurrentUserDep, db: DB) -> None:
    key = await _get(db, user.id, provider)
    await db.delete(key)
    await db.commit()


@router.post("/keys/{provider}/verify", status_code=status.HTTP_202_ACCEPTED)
async def reverify_key(provider: Provider, user: CurrentUserDep, db: DB) -> ProviderKeyOut:
    from doctune.workers.tasks.keys import verify_key

    key = await _get(db, user.id, provider)
    verify_key.delay(str(user.id), provider.value)
    return _out(key)
