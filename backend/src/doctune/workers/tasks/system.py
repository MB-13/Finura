import structlog

from doctune.workers.celery_app import app

log = structlog.get_logger()


@app.task(name="doctune.workers.tasks.system.ping")
def ping() -> str:
    return "pong"


@app.task(name="doctune.workers.tasks.system.beat_heartbeat")
def beat_heartbeat() -> None:
    """Also keeps a free Supabase project active (it pauses after a week without queries)."""
    from sqlalchemy import text

    from doctune.core.db import sync_session

    with sync_session() as db:
        db.execute(text("select 1"))
    log.info("beat_heartbeat")
