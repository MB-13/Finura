---
name: plan-feature
description: Produce a technical plan for a DocTune feature across frontend/, backend/, workers and notebook/ - API contract, data model, Celery tasks, status transitions, SSE, UI, tests - before writing code. Use when starting any non-trivial feature.
argument-hint: "[feature or PRD]"
---

# Plan feature

Feature: $ARGUMENTS

1. Read `CLAUDE.md`, the relevant `docs/design/doctune-design.md` sections, and any `docs/prd/*.md`.
2. Explore existing code in `frontend/`, `backend/`, `notebook/` for patterns to reuse.
3. Delegate the design to **system-architect**. Pull in specialists as needed:
   - **database-engineer** for schema changes
   - **pipeline-engineer** for parsing / generation / judge / RAG work
   - **ml-engineer** for notebook, training, export, playground inference
4. Present the plan: components touched, API contract, data changes, async flow and status edges, UI states, risks, test plan, ordered steps.
5. Record significant decisions as an ADR in `docs/adr/`.
6. Wait for the user's approval before `/new-feature`.
