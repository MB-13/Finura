---
name: new-feature
description: Implement a DocTune feature end-to-end across backend/ (FastAPI + Celery), frontend/ (React) and notebook/ in the right order - schema, API contract, workers, generated types, UI, tests. Use when the user asks to build or implement a feature.
argument-hint: "[feature]"
---

# New feature

Feature: $ARGUMENTS. If there's no approved plan, run `/plan-feature` first.

## Order (contract-first)
1. **Schema** — models + migration (`/db-migration`) → `database-engineer`.
2. **API contract** — Pydantic schemas + routers + services (`/api-endpoint`) → `backend-developer`. Status changes via the transition service.
3. **Async work** — Celery tasks (`/celery-task`) → `pipeline-engineer`.
4. **Notebook** (if training-related) — `/notebook-change` → `ml-engineer`.
5. **Types** — `/sync-api-types` so `frontend/` sees the new contract.
6. **UI** — pages/components (`/ui-component`) → `frontend-developer`, polish → `ui-designer`.
7. **Tests** — `/write-tests` → `test-engineer`.
8. **Verify** — `/ship-check`.

Run independent steps (e.g. worker + UI once the contract is fixed) with parallel agents.

Report: what was built per layer, files changed, how to try it locally, anything not verified.
