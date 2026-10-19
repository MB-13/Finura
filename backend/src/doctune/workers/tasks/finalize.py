import uuid
from datetime import UTC, datetime, timedelta

import structlog

from doctune.core import events
from doctune.core.db import sync_session
from doctune.models.enums import ProjectStatus
from doctune.models.generation import GenerationRun, GenState
from doctune.models.project import Project
from doctune.services.generation import finalize_pairs
from doctune.services.projects import transition_sync
from doctune.services.transitions import Actor
from doctune.workers.celery_app import app

log = structlog.get_logger()


@app.task(name="doctune.workers.tasks.finalize.finalize_run", soft_time_limit=900, time_limit=960)
def finalize_run(run_id: str) -> None:
    """Dedupe, trim to target, split 90/10, then hand the dataset to the user for review."""
    rid = uuid.UUID(run_id)
    with sync_session() as db:
        run = db.get(GenerationRun, rid, with_for_update=True)
        if run is None or run.state != GenState.finalizing:
            return
        project = db.get(Project, run.project_id)
        assert project is not None
        events.publish(run.project_id, "progress", {"phase": "finalize", "run_id": run_id})
        result = finalize_pairs(db, run, project)
        run.state, run.pairs_kept, run.finished_at = GenState.done, result.kept, datetime.now(UTC)
        long_running = run.started_at is not None and run.finished_at - run.started_at > timedelta(minutes=10)
        db.commit()
        log.info("run_finalized", run_id=run_id, kept=result.kept, dropped=result.dropped)

        if result.kept == 0:
            transition_sync(
                db,
                run.project_id,
                ProjectStatus.failed,
                actor=Actor.worker,
                reason="no_pairs_kept",
                message="None of the generated pairs passed the quality check. Try clearer style examples or "
                "different documents.",
                retry_to=ProjectStatus.awaiting_style,
                if_status=ProjectStatus.generating,
            )
            return
        moved = transition_sync(
            db,
            run.project_id,
            ProjectStatus.in_review,
            actor=Actor.worker,
            if_status=ProjectStatus.generating,
        )
    if moved and long_running:
        from doctune.workers.tasks.notify import send_email

        send_email.delay("dataset_ready", str(run.project_id), f"run:{rid}:ready")
