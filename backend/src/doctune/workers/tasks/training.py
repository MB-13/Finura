"""Training housekeeping on the beat: heartbeat monitor, token reminders, retention."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update

from doctune.core.db import sync_session
from doctune.core.storage import get_storage
from doctune.models.enums import ProjectStatus
from doctune.models.training import Artifact, JobState, JobToken, PauseReason, TrainingJob
from doctune.routers.notebook import pause_message
from doctune.services.projects import transition_sync
from doctune.services.transitions import Actor
from doctune.workers.celery_app import app

log = structlog.get_logger()
HEARTBEAT_TIMEOUT = timedelta(minutes=15)
RETENTION = timedelta(days=14)


@app.task(name="doctune.workers.tasks.training.monitor_heartbeats")
def monitor_heartbeats() -> int:
    """A running job with no heartbeat for 15 minutes is paused (and the user emailed once)."""
    from doctune.workers.tasks.notify import send_email

    cutoff = datetime.now(UTC) - HEARTBEAT_TIMEOUT
    paused = 0
    with sync_session() as db:
        stale = db.scalars(
            select(TrainingJob).where(TrainingJob.state == JobState.running, TrainingJob.last_heartbeat_at < cutoff)
        ).all()
        for job in stale:
            claimed = db.execute(
                update(TrainingJob)
                .where(TrainingJob.id == job.id, TrainingJob.state == JobState.running)
                .values(state=JobState.paused, pause_reason=PauseReason.heartbeat_timeout, paused_at=datetime.now(UTC))
                .returning(TrainingJob.id)
            ).first()
            db.commit()
            if not claimed:
                continue
            message = pause_message(PauseReason.heartbeat_timeout, job.current_step, job.max_steps, job.backend)
            moved = transition_sync(
                db,
                job.project_id,
                ProjectStatus.paused,
                actor=Actor.monitor,
                reason="heartbeat_timeout",
                message=message,
                if_status=ProjectStatus.training,
            )
            if moved:
                paused += 1
                from doctune.workers.tasks.models import convert_adapter

                convert_adapter.delay(str(job.id), "checkpoint")
                pct = str(int(100 * job.current_step / max(job.max_steps, 1)))
                if job.backend == "colab" or job.launch_attempts >= 3:
                    send_email.delay(
                        "paused",
                        str(job.project_id),
                        f"job:{job.id}:pause:{job.current_step}",
                        {"message": message, "percent": pct},
                    )
    return paused


@app.task(name="doctune.workers.tasks.training.token_reminders")
def token_reminders() -> int:
    from doctune.workers.tasks.notify import send_email

    now = datetime.now(UTC)
    with sync_session() as db:
        rows = db.execute(
            select(TrainingJob.project_id, JobToken.id)
            .join(JobToken, JobToken.job_id == TrainingJob.id)
            .where(
                TrainingJob.state.in_([JobState.created, JobState.running, JobState.paused]),
                JobToken.revoked_at.is_(None),
                JobToken.expires_at.between(now, now + timedelta(days=2)),
            )
        ).all()
    for project_id, token_id in rows:
        send_email.delay("token_expiring", str(project_id), f"token:{token_id}:expiring")
    return len(rows)


@app.task(name="doctune.workers.tasks.training.cleanup_retention")
def cleanup_retention() -> int:
    """Delete job files 14 days after the job ended (design doc storage policy)."""
    cutoff = datetime.now(UTC) - RETENTION
    storage = get_storage()
    cleaned = 0
    with sync_session() as db:
        jobs = db.scalars(
            select(TrainingJob).where(TrainingJob.ended_at < cutoff, TrainingJob.ended_at.is_not(None))
        ).all()
        for job in jobs:
            arts = db.scalars(select(Artifact).where(Artifact.job_id == job.id, Artifact.uploaded)).all()
            if not arts and not storage.head(f"j/{job.id}/checkpoint/latest.zip"):
                continue
            storage.delete_prefix(f"j/{job.id}/")
            for art in arts:
                art.uploaded = False
            cleaned += 1
        db.commit()
    log.info("retention_cleanup", jobs=cleaned)
    return cleaned
