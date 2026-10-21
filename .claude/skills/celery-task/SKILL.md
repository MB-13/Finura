---
name: celery-task
description: Create or modify a DocTune Celery task (parse, generate preview/full, judge, dedupe/split, embed, heartbeat monitor) - idempotent, retry-safe, rate-limit aware with provider fallback, progress reported for SSE, status transitions via the service. Use for any background work in backend/src/doctune/workers.
argument-hint: "[task name and purpose]"
---

# Celery task

Task: $ARGUMENTS. Load `backend-conventions`; delegate non-trivial work to **pipeline-engineer**.

## Template
```py
# backend/src/doctune/workers/tasks/generate.py
from doctune.workers.celery_app import app
from doctune.llm.client import ProvidersExhausted, generate_pairs
from doctune.services import projects as project_service, progress

@app.task(bind=True, acks_late=True, max_retries=5, autoretry_for=(ConnectionError,), retry_backoff=True)
def generate_chunk(self, project_id: str, chunk_id: str) -> None:
    with sync_session() as db:
        if progress.chunk_done(db, project_id, chunk_id):      # idempotent: skip if already processed
            return
        try:
            pairs = generate_pairs(db, project_id, chunk_id)   # uses user's keys + fallback chain
        except ProvidersExhausted as exc:
            project_service.pause_generation(db, project_id, reason="provider_quota")
            raise self.retry(exc=exc, countdown=exc.retry_after or 3600)
        progress.save_pairs(db, project_id, chunk_id, pairs)   # also bumps progress for SSE
```

## Checklist
- [ ] Idempotent: safe to run twice (check-then-write, unique constraints)
- [ ] `acks_late`, bounded retries with backoff; no infinite retry storms
- [ ] Rate limits: back off → next connected provider → pause + scheduled resume when all exhausted
- [ ] Fan-out via `group`/`chord`; final step does judge → dedupe → 10% split → `in_review`
- [ ] Progress persisted so SSE can stream it
- [ ] Status via `transition()`; unrecoverable error → `failed` with a user-readable message
- [ ] Timeouts (`soft_time_limit`) for parsing and LLM calls; parsing runs isolated
- [ ] Never log API keys or full document text
- [ ] pytest with mocked providers (success, broken JSON, 429, all exhausted) and re-run idempotency
