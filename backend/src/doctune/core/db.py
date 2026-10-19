from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from doctune.core.config import get_settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


@lru_cache
def get_engine() -> AsyncEngine:
    # statement_cache_size=0 keeps asyncpg compatible with Supabase's transaction pooler
    return create_async_engine(
        get_settings().database_url, pool_pre_ping=True, connect_args={"statement_cache_size": 0}
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


@lru_cache
def _sync_sessionmaker() -> sessionmaker[Session]:
    engine = create_engine(get_settings().database_url_sync, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def sync_session() -> Iterator[Session]:
    """Session for Celery tasks (workers are synchronous)."""
    with _sync_sessionmaker()() as session:
        yield session
