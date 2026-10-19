import uuid
from datetime import UTC, datetime, timedelta

import structlog
from celery import Task
from sqlalchemy import select, update

from doctune.core import events
from doctune.core.db import sync_session
from doctune.llm.client import BadModelOutput, LLMError, NoProviders, ProvidersExhausted, UpstreamError
from doctune.models.document import Chunk
from doctune.models.enums import ProjectStatus
from doctune.models.generation import (
    DatasetPair,
    GenerationRun,
    GenerationUnit,
    GenKind,
    GenState,
    StyleConfig,
    UnitState,
)
from doctune.models.project import Project
from doctune.services import generation as gen
from doctune.services.projects import transition_sync
from doctune.services.style import to_spec
from doctune.services.transitions import Actor
from doctune.workers.celery_app import app

log = structlog.get_logger()


def _progress(run: GenerationRun, phase: str) -> None:
    events.publish(
        run.project_id,
        "progress",
        {
            "phase": phase,
            "run_id": str(run.id),
            "done": run.done_chunks,
            "total": run.total_chunks,
            "pairs": run.pairs_generated,
            "state": run.state,
        },
    )


# ---------------- preview ----------------


@app.task(name="doctune.workers.tasks.generate.generate_preview", soft_time_limit=600, time_limit=660)
def generate_preview(run_id: str) -> None:
    """Small, sequential: a few chunks, judged, then back to the style screen."""
    rid = uuid.UUID(run_id)
    with sync_session() as db:
        run = db.get(GenerationRun, rid)
        if run is None or run.state != GenState.queued:
            return
        project = db.get(Project, run.project_id)
        style = db.get(StyleConfig, run.style_id)
        assert project is not None and style is not None
        run.state, run.started_at = GenState.running, datetime.now(UTC)
        db.commit()
        spec = to_spec(style)
        llm = gen.make_llm(db, project, run.user_id)
        units = db.scalars(select(GenerationUnit).where(GenerationUnit.run_id == rid)).all()
        error: str | None = None
        try:
            for unit in units:
                chunk = db.get(Chunk, unit.chunk_id)
                assert chunk is not None
                pairs, t_in, t_out = gen.generate_pairs(llm, spec, chunk.text, run.pairs_per_chunk)
                rows = [
                    DatasetPair(
                        project_id=run.project_id,
                        run_id=rid,
                        chunk_id=chunk.id,
                        dataset_format=style.dataset_format,
                        question=q,
                        answer=a,
                        record=record,
                        preview=True,
                    )
                    for q, a, record in pairs
                ]
                db.add_all(rows)
                db.flush()
                j_in, j_out = gen.judge(llm, spec, chunk.text, rows)
                gen.add_tokens(db, rid, t_in + j_in, t_out + j_out, len(rows))
                unit.state, unit.generated, unit.judged = UnitState.done, True, True
                run.done_chunks += 1
                db.commit()
                _progress(run, "preview")
        except ProvidersExhausted as exc:
            error = f"Your providers are rate-limited for about {int(exc.retry_after // 60) + 1} min. Try again later."
        except NoProviders as exc:
            error = str(exc)
        except LLMError:
            log.exception("preview_failed", run_id=run_id)
            error = "The AI provider didn't respond properly. Please try again."
        db.rollback() if error else None
        run = db.get(GenerationRun, rid)
        assert run is not None
        run.state = GenState.failed if error else GenState.done
        run.error = error
        run.finished_at = datetime.now(UTC)
        db.commit()
        transition_sync(
            db,
            run.project_id,
            ProjectStatus.awaiting_style,
            actor=Actor.worker,
            reason="preview_failed" if error else None,
            message=error,
            if_status=ProjectStatus.previewing,
        )


# ---------------- full run ----------------


def dispatch(run_id: uuid.UUID, lanes: int = 1) -> int:
    with sync_session() as db:
        state = db.scalar(select(GenerationRun.state).where(GenerationRun.id == run_id))
        if state != GenState.running:
            return 0
        chunk_ids = gen.claim_pending_units(db, run_id, lanes)
    for chunk_id in chunk_ids:
        process_unit.delay(str(run_id), str(chunk_id))
    return len(chunk_ids)


@app.task(name="doctune.workers.tasks.generate.start_full_run")
def start_full_run(run_id: str) -> None:
    rid = uuid.UUID(run_id)
    with sync_session() as db:
        claimed = db.execute(
            update(GenerationRun)
            .where(GenerationRun.id == rid, GenerationRun.state == GenState.queued)
            .values(state=GenState.running, started_at=datetime.now(UTC))
            .returning(GenerationRun.id)
        ).first()
        db.commit()
    if claimed:
        dispatch(rid, gen.LANES)


@app.task(
    bind=True,
    name="doctune.workers.tasks.generate.process_unit",
    soft_time_limit=300,
    time_limit=330,
    max_retries=3,
)
def process_unit(self: Task, run_id: str, chunk_id: str) -> None:  # type: ignore[type-arg]
    rid, cid = uuid.UUID(run_id), uuid.UUID(chunk_id)
    finished = False
    with sync_session() as db:
        run = db.get(GenerationRun, rid)
        unit = db.get(GenerationUnit, (rid, cid))
        if run is None or unit is None or run.state not in (GenState.running, GenState.waiting_quota):
            return
        if unit.state in (UnitState.done, UnitState.failed, UnitState.cancelled):
            return
        project = db.get(Project, run.project_id)
        style = db.get(StyleConfig, run.style_id)
        chunk = db.get(Chunk, cid)
        assert project is not None and style is not None
        if chunk is None:
            unit.state, unit.error = UnitState.failed, "chunk removed"
            db.commit()
            finished = True
        else:
            spec = to_spec(style)
            llm = gen.make_llm(db, project, run.user_id)
            try:
                if not unit.generated:
                    avoid = gen.existing_questions(db, run, cid)
                    pairs, t_in, t_out = gen.generate_pairs(llm, spec, chunk.text, run.pairs_per_chunk, avoid)
                    if not _still_active(db, rid):
                        db.rollback()
                        return
                    db.add_all(
                        DatasetPair(
                            project_id=run.project_id,
                            run_id=rid,
                            chunk_id=cid,
                            dataset_format=style.dataset_format,
                            question=q,
                            answer=a,
                            record=record,
                        )
                        for q, a, record in pairs
                    )
                    unit.generated = True
                    gen.add_tokens(db, rid, t_in, t_out, len(pairs))
                    db.commit()
                if not unit.judged:
                    rows = list(
                        db.scalars(select(DatasetPair).where(DatasetPair.run_id == rid, DatasetPair.chunk_id == cid))
                    )
                    j_in, j_out = gen.judge(llm, spec, chunk.text, rows)
                    if not _still_active(db, rid):
                        db.rollback()
                        return
                    unit.judged = True
                    gen.add_tokens(db, rid, j_in, j_out)
                unit.state = UnitState.done
                db.commit()
                finished = True
            except ProvidersExhausted as exc:
                db.rollback()
                unit = db.get(GenerationUnit, (rid, cid))
                assert unit is not None
                unit.state = UnitState.pending
                db.commit()
                resume_at = gen.pause_for_quota(db, run, exc.retry_after)
                events.publish(
                    run.project_id,
                    "notice",
                    {
                        "level": "warning",
                        "text": "Your providers hit their free limits. Generation continues "
                        f"automatically at {resume_at:%H:%M} UTC.",
                        "resume_at": resume_at.isoformat(),
                    },
                )
                from doctune.workers.tasks.notify import send_email

                send_email.delay(
                    "generation_waiting_quota",
                    str(run.project_id),
                    f"run:{rid}:quota",
                    {"when": f" (around {resume_at:%H:%M} UTC)"},
                )
                return
            except NoProviders as exc:
                db.rollback()
                fail_run(db, rid, str(exc), reason="no_providers")
                return
            except (BadModelOutput, UpstreamError) as exc:
                db.rollback()
                unit = db.get(GenerationUnit, (rid, cid))
                assert unit is not None
                unit.attempts += 1
                if unit.attempts < 3 and isinstance(exc, UpstreamError):
                    db.commit()
                    raise self.retry(countdown=30 * unit.attempts, exc=exc) from exc
                unit.state, unit.error = UnitState.failed, str(exc)[:500]
                db.commit()
                finished = True

        if finished:
            run = db.get(GenerationRun, rid)
            assert run is not None
            db.refresh(run)
            _progress(run, "generate")
            last = gen.count_unit(db, rid)
    if finished:
        if last:
            from doctune.workers.tasks.finalize import finalize_run

            finalize_run.delay(run_id)
        else:
            dispatch(rid, 1)


def _still_active(db: object, run_id: uuid.UUID) -> bool:
    """Lock the run row before writing a unit's results. Finishing early or cancelling takes the same lock,
    so results either land before finalize reads them or are dropped."""
    from sqlalchemy.orm import Session

    assert isinstance(db, Session)
    state = db.scalar(select(GenerationRun.state).where(GenerationRun.id == run_id).with_for_update())
    return state in (GenState.running, GenState.waiting_quota)


def fail_run(db: object, run_id: uuid.UUID, message: str, reason: str) -> None:
    from sqlalchemy.orm import Session

    assert isinstance(db, Session)
    run = db.get(GenerationRun, run_id)
    if run is None:
        return
    run.state, run.error, run.finished_at = GenState.failed, message, datetime.now(UTC)
    db.execute(
        update(GenerationUnit)
        .where(GenerationUnit.run_id == run_id, GenerationUnit.state.in_([UnitState.pending, UnitState.queued]))
        .values(state=UnitState.cancelled)
    )
    db.commit()
    transition_sync(
        db,
        run.project_id,
        ProjectStatus.failed,
        actor=Actor.worker,
        reason=reason,
        message=message,
        retry_to=ProjectStatus.awaiting_style,
        if_status=ProjectStatus.generating,
    )


@app.task(name="doctune.workers.tasks.generate.resume_runs")
def resume_runs() -> int:
    """Beat: restart runs whose quota wait is over, and re-dispatch runs that stalled."""
    now = datetime.now(UTC)
    resumed: list[uuid.UUID] = []
    with sync_session() as db:
        due = db.scalars(
            update(GenerationRun)
            .where(GenerationRun.state == GenState.waiting_quota, GenerationRun.resume_at <= now)
            .values(state=GenState.running, resume_at=None)
            .returning(GenerationRun.id)
        ).all()
        resumed.extend(due)
        stalled = db.scalars(
            select(GenerationRun.id).where(
                GenerationRun.state == GenState.running,
                GenerationRun.kind == GenKind.full,
                GenerationRun.updated_at < now - timedelta(minutes=30),
            )
        ).all()
        if stalled:
            db.execute(
                update(GenerationUnit)
                .where(GenerationUnit.run_id.in_(stalled), GenerationUnit.state == UnitState.queued)
                .values(state=UnitState.pending)
            )
            resumed.extend(stalled)
        db.commit()
    for rid in resumed:
        dispatch(rid, gen.LANES)
    return len(resumed)
