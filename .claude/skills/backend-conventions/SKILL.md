---
name: backend-conventions
description: Conventions for DocTune's FastAPI service and Celery workers (backend/) - layering, auth modes, status transitions, async-only slow work, R2, encryption, LLM client, errors, typing, testing. Load whenever writing or reviewing code under backend/.
user-invocable: false
---

# backend/ conventions

## Layering
`routers/` (HTTP only) → `services/` (business rules, ownership, transitions) → `models/` (SQLAlchemy). `schemas/` holds Pydantic in/out models. Routers never touch the ORM directly beyond passing the session; services never import FastAPI.

## Auth
- `current_user`: verifies Supabase JWT (JWKS, `aud`, `exp`) → `CurrentUser(id, email)`.
- `current_job`: `Authorization: Bearer <job token>` → hash → lookup → not expired (14 days) / not revoked → `CurrentJob`. Only `/jobs/current/*` uses it.
- Services take `user_id` and scope every query by ownership; not found and not owned both return 404.

## Status
`services/projects.transition(db, project, to, actor, reason=None)` validates the edge and actor against the CLAUDE.md table, sets `status_reason` for `paused`/`failed`, publishes an SSE event. Nothing else writes `status`.

## Slow work
Requests never parse, call LLMs, embed, or move big files. Enqueue a Celery task and return (202). Tasks: idempotent, `acks_late`, bounded retries, `soft_time_limit`.

## Storage
`core/r2.py` issues pre-signed GET/PUT with short TTL, exact keys (`users/{uid}/projects/{pid}/...`, `jobs/{jid}/checkpoint/latest.zip`, `jobs/{jid}/adapter/`), content-type/length constraints. Keep only the latest checkpoint; artifacts expire 14 days after job end.

## Secrets
`core/crypto.py` encrypts provider keys (Fernet/AES-GCM, key from env, key version stored). Keys are decrypted only inside workers at call time, never logged (Sentry `before_send` scrubs them), returned masked (`gsk_…abcd`).

## LLM client
`llm/client.py`: one OpenAI-compatible client, `base_url` per provider (Groq default, Gemini, Cerebras). Fallback chain over the user's connected providers; `ProvidersExhausted` → pause + scheduled resume. Prompts are versioned templates in `llm/prompts/`. Model JSON validated with Pydantic.

## Training backend
`training/base.py` protocol: `submit_job`, `get_status`, `get_output`, `cancel`. `training/colab.py` implements it via job tokens + heartbeats. Never special-case Colab outside this module.

## Errors & responses
Every route has `response_model` and explicit status codes. Domain errors are typed exceptions mapped to HTTP by handlers (`NotFound`→404, `InvalidTransition`→409, `LimitExceeded`→413/422, `RateLimited`→429). Error bodies: `{"error": code, "message": str}`.

## Code
Python 3.12, full type hints, `mypy --strict` on `src`, ruff (lint + format). Async SQLAlchemy in the API; sync sessions inside Celery tasks. Settings via `pydantic-settings` in `core/config.py`. Logging is structured JSON; no PII/keys/document text.

## Tests
pytest + pytest-asyncio, real Postgres for DB tests, `respx` for LLM HTTP, fake R2. Factories for users/projects.
