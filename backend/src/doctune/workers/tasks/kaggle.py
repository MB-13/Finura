"""Kaggle training backend workers (ADR-0002): account checks, kernel launch, and the status poll on the beat.

Tokens are decrypted only inside these tasks and passed straight to the client; nothing here logs or stores them.
"""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import structlog
from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import Session

from doctune.core import events, jobauth
from doctune.core.config import get_settings
from doctune.core.crypto import KeyDecryptError, decrypt
from doctune.core.db import sync_session
from doctune.core.errors import AppError
from doctune.models.compute import ComputeAccount, ComputeStatus
from doctune.models.enums import ProjectStatus
from doctune.models.project import Project
from doctune.models.training import Checkpoint, JobState, PauseReason, TrainingJob
from doctune.services.projects import transition_sync
from doctune.services.transitions import Actor
from doctune.training import catalog
from doctune.training.kaggle_client import (
    GpuQuota,
    KaggleAuthError,
    KaggleClient,
    KaggleError,
    KaggleQuotaError,
    KaggleRateLimited,
)
from doctune.training.kaggle_kernel import build_source, session_timeout_seconds
from doctune.training.presets import estimate_minutes
from doctune.workers.celery_app import app

log = structlog.get_logger()

ACTIVE_STATES = (JobState.created, JobState.running, JobState.paused)
POLLED_STATES = (*ACTIVE_STATES, JobState.evaluating)
MAX_LAUNCHES = 3
MAX_LAUNCH_RETRIES = 5
ENDED_GRACE = timedelta(minutes=2)  # let the kernel's last API calls land before judging a finished run
RESUMABLE_PAUSES = (
    PauseReason.session_ended,
    PauseReason.heartbeat_timeout,
    PauseReason.idle_timeout,
    PauseReason.no_gpu,  # also how a run waiting for Kaggle's weekly quota is parked
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}  # noqa: S104 - a deny-list, not a bind address


def _get_account(db: Session, user_id: uuid.UUID) -> ComputeAccount | None:
    return db.scalar(
        select(ComputeAccount).where(ComputeAccount.user_id == user_id, ComputeAccount.provider == "kaggle")
    )


def apply_quota(account: ComputeAccount, quota: GpuQuota) -> None:
    account.gpu_used_s = quota.used_s + quota.reserved_s
    account.gpu_total_s = quota.total_s
    account.quota_refresh_at = quota.refresh_at
    if quota.total_s <= 0:
        account.status = ComputeStatus.no_gpu_quota
        account.status_message = (
            "Kaggle gives this account no GPU time. Verify your phone number in your Kaggle settings, then re-check."
        )
    else:
        account.status = ComputeStatus.ok
        account.status_message = None
    account.checked_at = datetime.now(UTC)


def quota_message(quota: GpuQuota | None) -> str:
    when = quota.refresh_at.strftime("%Y-%m-%d %H:%M UTC") if quota and quota.refresh_at else "soon"
    return f"Your Kaggle weekly GPU quota is used up. It resets at {when}."


@app.task(name="doctune.workers.tasks.kaggle.check_kaggle_account", soft_time_limit=60)
def check_kaggle_account(user_id: str) -> str:
    """Validate the stored token and read the weekly GPU quota. Network trouble leaves the status untouched."""
    with sync_session() as db:
        account = _get_account(db, uuid.UUID(user_id))
        if account is None:
            return "missing"
        try:
            secret = decrypt(account.ciphertext)
        except KeyDecryptError:
            account.status, account.status_message = ComputeStatus.invalid, "Please enter your Kaggle token again."
            db.commit()
            return account.status
        try:
            with KaggleClient(account.username, secret, timeout=20) as kg:
                quota = kg.gpu_quota()
                kernels_ok = True
                try:
                    kg.check_kernel_access()
                except KaggleAuthError:
                    kernels_ok = False
        except KaggleAuthError:
            account.status = ComputeStatus.invalid
            account.status_message = "Kaggle rejected this username or token. Check both and try again."
            account.checked_at = datetime.now(UTC)
        except KaggleError as exc:
            log.warning("kaggle_check_inconclusive", transient=exc.transient)
            account.status_message = "Couldn't reach Kaggle just now. Try the check again in a minute."
            db.commit()
            return account.status
        else:
            apply_quota(account, quota)
            if not kernels_ok:
                account.status = ComputeStatus.invalid
                account.status_message = (
                    "This token can read your GPU quota but can't run Kaggle notebooks. "
                    "Create a new token on Kaggle → Settings → API and connect it again."
                )
        db.commit()
        return account.status


def _notify_failed(job: TrainingJob, message: str) -> None:
    from doctune.workers.tasks.notify import send_email

    send_email.delay("job_failed", str(job.project_id), f"job:{job.id}:failed", {"message": message})


def fail_job(db: Session, job: TrainingJob, message: str, *, reason: str = "kaggle_failed") -> None:
    """End a Kaggle job and fail its project (retry goes back to review)."""
    job.state, job.error, job.ended_at = JobState.failed, message[:2000], datetime.now(UTC)
    jobauth.revoke_all_sync(db, job.id)
    db.commit()
    project = db.get(Project, job.project_id)
    if project is not None and project.status in (
        ProjectStatus.awaiting_run,
        ProjectStatus.training,
        ProjectStatus.paused,
        ProjectStatus.evaluating,
    ):
        try:
            transition_sync(
                db,
                job.project_id,
                ProjectStatus.failed,
                actor=Actor.worker,
                reason=reason,
                message=message[:500],
                retry_to=ProjectStatus.in_review,
            )
        except AppError:
            log.warning("kaggle_fail_transition_skipped", project_id=str(job.project_id))
            db.rollback()
    _notify_failed(job, message)


def pause_for_quota(db: Session, job: TrainingJob, quota: GpuQuota | None) -> None:
    """A run that already started waits for the quota to reset; the poll relaunches it afterwards."""
    message = quota_message(quota) + " Training continues automatically then."
    if job.state != JobState.paused or job.pause_reason != PauseReason.no_gpu:
        job.state, job.pause_reason, job.paused_at = JobState.paused, PauseReason.no_gpu, datetime.now(UTC)
        db.commit()
        transition_sync(
            db,
            job.project_id,
            ProjectStatus.paused,
            actor=Actor.monitor,
            reason=PauseReason.no_gpu.value,
            message=message,
            if_status=ProjectStatus.training,
        )


def _estimate_minutes(job: TrainingJob) -> float:
    model = catalog.BY_ID.get(job.base_model_id)
    sec_per_step, startup = (model.sec_per_step, model.startup_min) if model else (5.0, 3.0)
    return estimate_minutes(job.max_steps, sec_per_step, startup, 200.0)


def _api_url_ok(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return bool(host) and host not in LOCAL_HOSTS


@app.task(
    name="doctune.workers.tasks.kaggle.launch_kaggle_job",
    bind=True,
    max_retries=MAX_LAUNCH_RETRIES,
    soft_time_limit=180,
    acks_late=True,
)
def launch_kaggle_job(self: Task, job_id: str, attempt: int = 1) -> str:  # type: ignore[type-arg]
    """Push (or re-push) the private kernel for a job. Idempotent per `attempt`."""
    jid = uuid.UUID(job_id)
    settings = get_settings()
    with sync_session() as db:
        job = db.get(TrainingJob, jid)
        if job is None or job.backend != "kaggle" or job.state not in ACTIVE_STATES or job.launch_attempts >= attempt:
            return "skipped"
        account = _get_account(db, job.user_id)
        if account is None or account.status in (ComputeStatus.invalid, ComputeStatus.no_gpu_quota):
            fail_job(db, job, "Your Kaggle account isn't connected. Reconnect it in Settings, or use Colab instead.")
            return "failed"
        if not _api_url_ok(settings.public_api_url):
            fail_job(db, job, "DocTune's API isn't reachable from Kaggle in this environment (PUBLIC_API_URL).")
            return "failed"
        try:
            secret = decrypt(account.ciphertext)
        except KeyDecryptError:
            account.status, account.status_message = ComputeStatus.invalid, "Please enter your Kaggle token again."
            db.commit()
            fail_job(db, job, "Your Kaggle token needs to be entered again in Settings.")
            return "failed"
        username = account.username
        short = job.id.hex[:8]
        slug = f"doctune-{short}-{attempt}"
        timeout_s = session_timeout_seconds(_estimate_minutes(job))
        first_launch = job.state == JobState.created

        try:
            with KaggleClient(username, secret) as kg:
                quota: GpuQuota | None
                try:
                    quota = kg.gpu_quota()
                    apply_quota(account, quota)
                    db.commit()
                except KaggleError as exc:
                    if isinstance(exc, KaggleAuthError | KaggleRateLimited):
                        raise
                    quota = None  # the quota is a courtesy check; SaveKernel reports the real problems
                if quota is not None and quota.total_s <= 0:
                    fail_job(db, job, account.status_message or "Kaggle gives this account no GPU time.")
                    return "failed"
                if quota is not None and quota.exhausted:
                    if first_launch:
                        fail_job(db, job, quota_message(quota) + " Start training again after that, or use Colab.")
                        return "failed"
                    pause_for_quota(db, job, quota)
                    return "deferred"
                token = jobauth.issue_sync(db, job.id)
                db.commit()
                source = build_source(token, settings.public_api_url, job.id)
                saved = kg.save_kernel(slug, f"DocTune {short} {attempt}", source, session_timeout_s=timeout_s)
        except KaggleAuthError:
            account.status = ComputeStatus.invalid
            account.status_message = "Kaggle rejected this username or token. Reconnect it in Settings."
            db.commit()
            fail_job(db, job, "Kaggle rejected your username or token. Reconnect your account, or use Colab instead.")
            return "failed"
        except KaggleRateLimited as exc:
            db.rollback()
            if self.request.retries >= MAX_LAUNCH_RETRIES:
                fail_job(db, job, "Kaggle is busy right now. Please start training again in a few minutes.")
                return "failed"
            raise self.retry(exc=exc, countdown=exc.retry_after or min(30 * 2**self.request.retries, 600)) from exc
        except KaggleQuotaError as exc:
            fail_job(db, job, f"Kaggle refused to start the run: {exc.message}")
            return "failed"
        except KaggleError as exc:
            db.rollback()
            if exc.transient and self.request.retries < MAX_LAUNCH_RETRIES:
                raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 600)) from exc
            hint = " Make sure your Kaggle phone number is verified." if "phone" in exc.message.lower() else ""
            fail_job(db, job, f"Couldn't start the run on Kaggle: {exc.message}{hint}")
            return "failed"

        db.refresh(job)
        if job.state not in ACTIVE_STATES:  # cancelled while we were talking to Kaggle
            jobauth.revoke_all_sync(db, job.id)
            db.commit()
            return "cancelled"
        job.launch_attempts = attempt
        job.external_ref = saved.ref
        job.external_url = saved.url
        db.commit()
        events.publish(
            job.project_id,
            "progress",
            {"phase": "kaggle_launched", "attempt": attempt, "job_id": str(job.id), "url": saved.url},
        )
        log.info("kaggle_launched", job_id=job_id, attempt=attempt)
        return "launched"


def _ended_message(failure: str | None, url: str | None) -> str:
    detail = (failure or "").strip().replace("\n", " ")[:300]
    base = f"Kaggle stopped the training run{': ' + detail if detail else '.'}"
    tail = f" See the run log on Kaggle: {url}." if url else ""
    return f"{base}{tail} You can try again from your project, or use Colab instead."


def handle_ended_kernel(db: Session, job: TrainingJob, failure: str | None) -> str:
    """The kernel is gone but the job isn't finished: resume from the checkpoint, defer for quota, or fail."""
    started = job.started_at is not None
    if job.state == JobState.evaluating:
        fail_job(db, job, "The run ended while evaluating your model. " + _ended_message(failure, job.external_url))
        return "failed"
    has_checkpoint = db.get(Checkpoint, job.id) is not None
    session_end = job.state == JobState.paused and job.pause_reason in RESUMABLE_PAUSES
    if started and job.launch_attempts < MAX_LAUNCHES and (has_checkpoint or session_end):
        launch_kaggle_job.delay(str(job.id), job.launch_attempts + 1)
        return "relaunching"
    fail_job(db, job, _ended_message(failure, job.external_url))
    return "failed"


@app.task(name="doctune.workers.tasks.kaggle.poll_kaggle_jobs", soft_time_limit=110)
def poll_kaggle_jobs() -> dict[str, int]:
    """Beat: look at every live Kaggle run, relaunch interrupted ones, fail dead ones, revoke finished tokens."""
    counts = {"checked": 0, "relaunched": 0, "failed": 0, "revoked": 0}
    now = datetime.now(UTC)
    with sync_session() as db:
        # tokens of finished jobs must not stay valid
        finished = db.scalars(
            select(TrainingJob.id).where(
                TrainingJob.backend == "kaggle",
                TrainingJob.state.in_([JobState.completed, JobState.failed, JobState.cancelled]),
            )
        ).all()
        for job_id in finished:
            jobauth.revoke_all_sync(db, job_id)
        counts["revoked"] = len(finished)
        db.commit()

        jobs = db.scalars(
            select(TrainingJob).where(
                TrainingJob.backend == "kaggle",
                TrainingJob.state.in_(POLLED_STATES),
                TrainingJob.external_ref.is_not(None),
            )
        ).all()
        clients: dict[uuid.UUID, KaggleClient | None] = {}
        try:
            for job in jobs:
                if job.user_id not in clients:
                    account = _get_account(db, job.user_id)
                    try:
                        clients[job.user_id] = (
                            KaggleClient(account.username, decrypt(account.ciphertext), timeout=20) if account else None
                        )
                    except KeyDecryptError:
                        clients[job.user_id] = None
                kg = clients[job.user_id]
                assert job.external_ref is not None
                if kg is None:
                    continue
                try:
                    status = kg.session_status(job.external_ref.rsplit("/", 1)[-1])
                except KaggleRateLimited:
                    log.warning("kaggle_poll_rate_limited")
                    break
                except KaggleAuthError as exc:
                    if exc.status != 401:  # a denied permission on one kernel says nothing about the token
                        log.warning("kaggle_poll_denied", job_id=str(job.id), status=exc.status)
                        continue
                    account = _get_account(db, job.user_id)
                    if account is not None:
                        account.status = ComputeStatus.invalid
                        account.status_message = "Kaggle rejected this token. Reconnect your account in Settings."
                        db.commit()
                    continue
                except KaggleError:
                    continue
                counts["checked"] += 1
                if (
                    not status.ended
                    and job.state == JobState.created
                    and (job.runtime_info or {}).get("kaggle_status") != status.status
                ):
                    # before the kernel calls /start, show whether it is queued for a GPU or setting up
                    job.runtime_info = {**(job.runtime_info or {}), "kaggle_status": status.status}
                    db.commit()
                if not status.ended:
                    continue
                db.refresh(job)  # the kernel's final calls (finish, pause) may have landed meanwhile
                if job.state not in POLLED_STATES or now - job.updated_at < ENDED_GRACE:
                    continue
                outcome = handle_ended_kernel(db, job, status.failure_message)
                if outcome == "relaunching":
                    counts["relaunched"] += 1
                elif outcome == "failed":
                    counts["failed"] += 1
        finally:
            for kg in clients.values():
                if kg is not None:
                    kg.close()
    return counts
