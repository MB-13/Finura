---
name: db-migration
description: Change DocTune's database schema - SQLAlchemy models plus an Alembic migration on Supabase Postgres (+ pgvector). Use whenever a feature adds or changes tables, columns, enums, indexes or vector indexes.
argument-hint: "[description of the change]"
---

# DB migration

Change: $ARGUMENTS. Delegate design to **database-engineer** if non-trivial.

1. Update models in `backend/src/doctune/models/`:
   - ownership (`user_id` or FK path to it) + index
   - `created_at` / `updated_at`; explicit `ON DELETE` (project delete must cascade fully)
   - token/key columns store hashes / ciphertext only
2. `cd backend && uv run alembic revision --autogenerate -m "<message>"`
3. **Read the generated migration.** Autogenerate misses enum value changes, pgvector types/indexes, and server defaults — fix by hand. Ensure `downgrade()` works.
4. Destructive change? Expand → backfill → contract, and tell the user.
5. Apply **locally only**: `uv run alembic upgrade head` (asks for permission). Never run against Supabase staging/prod without explicit user confirmation.
6. Update Pydantic schemas, `uv run mypy src`, `uv run pytest`.

Summarize: schema diff, migration file, data risk, follow-ups (e.g. `/sync-api-types`).
