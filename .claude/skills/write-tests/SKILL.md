---
name: write-tests
description: Write DocTune tests for a feature, file or flow - pytest for FastAPI/services/Celery (mocked LLM providers and R2), Vitest + RTL for web components, Playwright for critical journeys, and notebook train.py smoke/resume tests. Use after implementing a feature or when asked to add coverage.
argument-hint: "[feature, file or flow]"
---

# Write tests

Target: $ARGUMENTS. Delegate to **test-engineer**.

| Layer | Location | Must cover |
|---|---|---|
| API routes | `backend/tests/routers/` | success, 422, 401, other user's resource, caps, bad status edge |
| Job-token endpoints | `backend/tests/routers/test_jobs.py` | valid, expired, revoked, wrong job |
| Services | `backend/tests/services/` | status transition table, ownership, encryption round-trip |
| Workers | `backend/tests/workers/` | parse fixtures, provider 429 → fallback → pause, broken JSON, idempotent re-run, heartbeat monitor |
| Web components | `frontend/src/**/*.test.tsx` | per-status rendering, forms, error states |
| E2E | `frontend/tests/e2e/` | critical journey only |
| Notebook | `notebook/tests/` | tiny-model smoke, checkpoint → resume at step N |

Run: `cd backend && uv run pytest`, `cd frontend && pnpm test` (+ `pnpm test:e2e` if added). Report real results; decide whether test or code is wrong before changing either.
