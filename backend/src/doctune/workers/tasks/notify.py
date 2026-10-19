"""User notifications by email, deduplicated through email_log."""

import uuid

import structlog
from sqlalchemy.dialects.postgresql import insert

from doctune.core.config import get_settings
from doctune.core.db import sync_session
from doctune.core.email import Email, send
from doctune.models.project import Project
from doctune.models.user import EmailLog, User
from doctune.workers.celery_app import app

log = structlog.get_logger()

TEMPLATES: dict[str, tuple[str, str]] = {
    "dataset_ready": (
        "Your dataset for {project} is ready to review",
        'DocTune finished generating the training data for "{project}".\n\nReview, edit and approve it here: {url}\n',
    ),
    "generation_waiting_quota": (
        "Generation for {project} is waiting for your free quota",
        'Your connected AI providers hit their free limits while generating data for "{project}".\n'
        "Nothing is lost — DocTune continues automatically when the quota resets{when}.\n\n"
        "Tip: connecting another free key (for example Gemini) makes generation faster.\n{url}\n",
    ),
    "paused": (
        "Training for {project} is paused at {percent}%",
        "{message}\n\nProgress is saved. Open the notebook and run it again to continue: {url}\n",
    ),
    "resumed": ("Training for {project} resumed", 'Training for "{project}" is running again.\n{url}\n'),
    "training_finished": (
        "Your model for {project} is ready",
        'Training finished for "{project}". Download it or try it in the playground: {url}\n',
    ),
    "job_failed": ("Training for {project} failed", "{message}\n\nDetails: {url}\n"),
    "token_expiring": (
        "Your DocTune job token for {project} expires soon",
        'The notebook token for "{project}" expires in 2 days. Rotate it from the project page if you still '
        "need to train: {url}\n",
    ),
}


@app.task(name="doctune.workers.tasks.notify.send_email", max_retries=3, default_retry_delay=120)
def send_email(kind: str, project_id: str, dedupe_key: str, data: dict[str, str] | None = None) -> bool:
    data = data or {}
    with sync_session() as db:
        project = db.get(Project, uuid.UUID(project_id))
        if project is None:
            return False
        user = db.get(User, project.user_id)
        if user is None or not user.email or not user.email_notifications:
            return False
        # claim the dedupe key first: a second attempt with the same key is a no-op
        claimed = db.execute(
            insert(EmailLog)
            .values(user_id=user.id, project_id=project.id, kind=kind, dedupe_key=dedupe_key)
            .on_conflict_do_nothing(index_elements=[EmailLog.dedupe_key])
            .returning(EmailLog.id)
        ).first()
        db.commit()
        if claimed is None:
            return False
        subject_t, body_t = TEMPLATES[kind]
        fields = {
            "project": project.name,
            "url": f"{get_settings().web_origin}/projects/{project.id}",
            "when": "",
            "percent": "",
            "message": "",
            **data,
        }
        email = Email(to=user.email, subject=subject_t.format(**fields), text=body_t.format(**fields))
    send(email)
    log.info("email_sent", kind=kind, project_id=project_id)
    return True
