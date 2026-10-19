"""One-job tokens for the training notebook: `dtj_` + 32 random bytes, stored only as a SHA-256 hash."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from doctune.core.db import get_session
from doctune.core.errors import Unauthorized
from doctune.models.training import JobState, JobToken, TrainingJob

PREFIX = "dtj_"
TOKEN_TTL = timedelta(days=14)


def new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class CurrentJob:
    job: TrainingJob
    token: JobToken


async def issue(db: AsyncSession, job_id: uuid.UUID) -> tuple[str, JobToken]:
    """Revoke any live token for the job and issue a new one. Returns the plaintext once."""
    now = datetime.now(UTC)
    await db.execute(
        update(JobToken).where(JobToken.job_id == job_id, JobToken.revoked_at.is_(None)).values(revoked_at=now)
    )
    token = new_token()
    row = JobToken(job_id=job_id, token_hash=hash_token(token), token_prefix=token[:10], expires_at=now + TOKEN_TTL)
    db.add(row)
    await db.flush()
    return token, row


async def revoke_all(db: AsyncSession, job_id: uuid.UUID) -> None:
    await db.execute(
        update(JobToken)
        .where(JobToken.job_id == job_id, JobToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def issue_sync(db: Session, job_id: uuid.UUID) -> str:
    """Worker-side `issue`: revoke live tokens, add a new one (caller commits). Returns the plaintext once."""
    now = datetime.now(UTC)
    db.execute(update(JobToken).where(JobToken.job_id == job_id, JobToken.revoked_at.is_(None)).values(revoked_at=now))
    token = new_token()
    db.add(JobToken(job_id=job_id, token_hash=hash_token(token), token_prefix=token[:10], expires_at=now + TOKEN_TTL))
    db.flush()
    return token


def revoke_all_sync(db: Session, job_id: uuid.UUID) -> None:
    db.execute(
        update(JobToken)
        .where(JobToken.job_id == job_id, JobToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def current_job(request: Request, db: Annotated[AsyncSession, Depends(get_session)]) -> CurrentJob:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith(PREFIX):
        raise Unauthorized("A DocTune job token is required.", code="token_missing")
    digest = hash_token(token)
    row = await db.scalar(select(JobToken).where(JobToken.token_hash == digest))
    if row is None or not hmac.compare_digest(row.token_hash, digest):
        raise Unauthorized("This job token isn't valid.", code="token_invalid")
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        raise Unauthorized("This job token was replaced or the job was cancelled.", code="token_revoked")
    if row.expires_at <= now:
        raise Unauthorized("This job token has expired. Create a new one from the project page.", code="token_expired")
    job = await db.get(TrainingJob, row.job_id, with_for_update=True)
    if job is None or job.state in (JobState.cancelled,):
        raise Unauthorized("This training job was cancelled.", code="token_revoked")
    if row.last_used_at is None or now - row.last_used_at > timedelta(minutes=1):
        row.last_used_at = now
    return CurrentJob(job=job, token=row)


CurrentJobDep = Annotated[CurrentJob, Depends(current_job)]
