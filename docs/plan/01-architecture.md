# 01 — Architecture

## 1. Components

| # | Component | Runs on | Tech | Responsibility |
|---|---|---|---|---|
| 1 | Frontend | Cloudflare Pages (static files) | React + Vite SPA, React Router, Tailwind, shadcn/ui, TanStack Query | All UI, rendered in the browser. Calls the API with the user's Supabase JWT |
| 2 | Auth | Supabase | Supabase Auth (email magic link + GitHub + Google OAuth) | Issues JWTs; API verifies them |
| 3 | API | Oracle VM (docker) | FastAPI, uvicorn | Records, validation, authz, pre-signed URLs, enqueue tasks, SSE, notebook endpoints |
| 4 | Queue | Oracle VM | Redis 7 | Celery broker + result backend + pub/sub for SSE + rate-limit counters |
| 5 | Workers | Oracle VM | Celery (queues: `parse`, `llm`, `embed`, `default`, `inference`) + beat | Parsing, generation, judge, dedupe, embedding, eval scoring, adapter conversion, monitor, cleanup, email |
| 6 | DB | Supabase | Postgres 15+ with pgvector | All state |
| 7 | Object storage | Cloudflare R2 | S3 API | Uploads, dataset JSONL, checkpoints, adapters |
| 8 | Training | User's Colab T4 | Jupyter notebook + Unsloth | Train, checkpoint, heartbeat, eval generations, export |
| 9 | Playground inference | Oracle VM | llama.cpp `llama-server` (+ inference manager) | Chat with base GGUF + LoRA, RAG context |
| — | Email | Resend | HTTP API | Pause/resume/finish/failure emails |
| — | Monitoring | Sentry, W&B (optional, user's own key in notebook) | | Errors; training curves |

Oracle Always Free ARM (Ampere A1): **2 OCPU / 12 GB RAM** (halved in June 2026; verified 2026-10-07). Memory budget:

| Service | RAM limit | CPU notes |
|---|---|---|
| OS + Caddy + Docker | 1.0 GB | |
| API (uvicorn, 2 workers) | 0.75 GB | light |
| Redis | 0.3 GB | |
| worker-parse (1 process, OCR) | 2.0 GB | bursts to 1 full core |
| worker-llm (threads, I/O) | 0.5 GB | light |
| worker-embed + worker-default (merged into one `worker-cpu` service, 2 processes) | 1.5 GB | e5-small ≈ 0.5 GB |
| beat | 0.15 GB | |
| llama-server (**one** warm model: ≤ 4B Q4_K_M + adapter, ctx 4096) | 4.0 GB | 2 threads; ~3–6 tok/s for 4B |
| headroom / page cache | ~1.8 GB | + 4 GB swap |

Two CPU cores are shared by parsing, embedding and the playground, so heavy jobs are serialized (concurrency 1) and the playground pauses new warm-ups while a parse is running.

## 2. Repo layout (monorepo)
```
doctune/
├─ frontend/                    React SPA (Vite, pnpm)
├─ backend/                     Python package `doctune` (uv)
│  ├─ src/doctune/
│  │  ├─ main.py                FastAPI app factory, routers, middleware, exception handlers
│  │  ├─ core/                  config.py, db.py, auth.py, jobauth.py, r2.py, crypto.py, email.py,
│  │  │                         ratelimit.py, events.py (Redis pub/sub), logging.py, errors.py
│  │  ├─ models/                SQLAlchemy models (one file per aggregate)
│  │  ├─ schemas/               Pydantic in/out models
│  │  ├─ routers/               me, keys, projects, documents, style, generation, dataset,
│  │  │                         models, training, jobs_notebook, events, playground, templates
│  │  ├─ services/              projects (transitions), documents, style, generation, dataset,
│  │  │                         keys, models_catalog, training, evaluation, playground, retention
│  │  ├─ llm/                   client.py, providers.py, prompts/*.jinja, parsing.py
│  │  ├─ parsing/               pdf.py, docx.py, text.py, ocr.py, chunker.py
│  │  ├─ embeddings/            encoder.py
│  │  ├─ training/              base.py (TrainingBackend protocol), colab.py, catalog.py, presets.py, hf_check.py
│  │  ├─ inference/             manager.py (llama-server lifecycle), rag.py
│  │  └─ workers/               celery_app.py, beat.py, tasks/{parse,generate,judge,finalize,embed,
│  │                            evaluate,convert,monitor,cleanup,email}.py
│  ├─ alembic/  tests/  pyproject.toml  Dockerfile
├─ notebook/
│  ├─ doctune_train.ipynb       thin: cells call functions in doctune_nb
│  ├─ doctune_nb/               pip-installable helper (api client, callbacks, train, eval, export)
│  └─ tests/
├─ infra/
│  ├─ docker-compose.yml  docker-compose.dev.yml  Caddyfile
│  ├─ llama/                    base GGUF download script, model manifest
│  └─ scripts/                  bootstrap-vm.sh, backup.sh
├─ docs/  .github/workflows/  .claude/  CLAUDE.md
```
`doctune_nb` is installed in the notebook with `pip install git+https://github.com/<org>/doctune@<tag>#subdirectory=notebook` pinned to a release tag, so notebook logic is versioned and testable instead of living in cells.

## 3. Request flow patterns

**A. Sync CRUD** — web → API → DB → response.
**B. Async job** — web → API: validate, write record, `transition()`, enqueue task, `202` → worker does work, updates DB, publishes event → API SSE → web cache update.
**C. Direct upload/download** — web → API: create record + pre-signed PUT → browser PUTs to R2 → web → API `complete` → API `HEAD`s object (size/type) → enqueue.
**D. Notebook** — notebook → API `/jobs/current/*` with job token → pre-signed URLs → R2.

## 4. Auth

### Web users
- Supabase Auth in browser (`@supabase/supabase-js`), methods: email magic link, GitHub, Google.
- API dependency `current_user`: read `Authorization: Bearer <jwt>` → verify with Supabase JWKS (`/auth/v1/.well-known/jwks.json`, cached 10 min, `PyJWKClient`), check `aud=authenticated`, `exp`, `iss` → upsert `users` row on first sight → `CurrentUser(id, email)`.
- Legacy HS256 secret supported via config flag in case the project uses it.

### Notebook job tokens
- Format: `dtj_` + 43 chars base64url (32 random bytes). Shown **once** to the user.
- Stored: `sha256(token)` in `job_tokens.token_hash` (unique). Lookup by hash, constant-time compare not needed after hash lookup but use `hmac.compare_digest` on hash.
- Valid when: not revoked, `now < expires_at` (created + 14 days), job not cancelled. Each use updates `last_used_at` (throttled to 1/min).
- Scope: only `/jobs/current/*`; resolves to exactly one `training_jobs` row.
- Regenerate token: revokes old, issues new (same job).

## 5. Project status machine

Statuses: `draft, uploaded, parsing, awaiting_style, previewing, generating, in_review, awaiting_run, training, paused, evaluating, ready, failed`.

| From | To | Actor | Trigger |
|---|---|---|---|
| draft | uploaded | api | first document upload completed |
| uploaded | parsing | user | "Process documents" |
| parsing | awaiting_style | worker:parse | all docs parsed, ≥1 chunk |
| parsing | failed | worker:parse | all docs failed / zero chunks |
| awaiting_style | previewing | user | "Generate preview" |
| previewing | awaiting_style | worker:generate | preview done (or preview failed: reason shown, not project failure) |
| awaiting_style | generating | user | "Generate full dataset" (requires ≥1 preview with current style hash) |
| generating | in_review | worker:finalize | judge + dedupe + split done |
| generating | failed | worker | unrecoverable (e.g. all keys invalid) |
| generating | awaiting_style | user | cancel generation |
| in_review | awaiting_style | user | "Change style & regenerate" (discards pairs after confirm) |
| in_review | generating | user | "Complete generation" (run finished early: generate the skipped sections) or "Generate more pairs" (another pass toward the target, avoiding existing questions). Both keep pairs and edits, clear any approval |
| in_review | awaiting_run | user | approve dataset + choose model + start training (creates dataset_version + job + token) |
| awaiting_run | training | notebook | first heartbeat |
| training | paused | notebook / monitor | notebook reports reason, or 15 min heartbeat silence |
| paused | training | notebook | heartbeat after resume |
| training | evaluating | notebook | training complete |
| evaluating | ready | notebook | artifacts uploaded |
| awaiting_run / paused | failed | worker | Kaggle launch failed / run given up (ADR-0002) |
| awaiting_run / training / paused | in_review | user | cancel job (revoke token) |
| ready | awaiting_run | user | "Train again" (new job, same or new model) — P7 |
| failed | (previous safe status) | user | "Retry" — target stored in `status_retry_to` |
| any | (deleted) | user | delete project (async purge) |

Implementation: `services/projects.py`
```py
ALLOWED: dict[tuple[Status, Status], set[Actor]]
async def transition(db, project, to, *, actor, reason=None, message=None) -> Project
```
- `SELECT … FOR UPDATE` on the project row; validate edge+actor; set `status`, `status_reason`, `status_message`, `status_changed_at`; append to `project_events`; commit; publish `project.status` event.
- Notebook heartbeats moving `paused → training` must be idempotent (a heartbeat while already `training` is a no-op).

## 6. Real-time events (SSE)
- Endpoint `GET /projects/{id}/events` (user JWT). Implementation: `sse-starlette`, subscribes Redis channel `proj:{id}`; sends `retry: 3000`, heartbeat comment every 15 s; first event is a full `snapshot`.
- Event types:
  - `snapshot` `{project}` (full ProjectOut)
  - `status` `{status, reason, message, at}`
  - `progress` `{phase: parse|preview|generate|judge|embed|train|eval, done, total, extra}`
  - `train_metrics` `{step, max_steps, loss, lr, at}` (throttled ≤1/5 s)
  - `notice` `{level, text}` (e.g. "Groq rate limited, switched to Cerebras")
- Web: `fetch-event-source` with Authorization header; on reconnect re-fetch project (snapshot).
- Publishing: `core/events.py publish(project_id, type, data)` — used from API and workers (sync Redis client in workers).

## 7. Storage layout (local disk now, single private R2 bucket `doctune` later — D20)
Keys are identical for both backends. `LocalStorage` serves signed URLs at `{PUBLIC_API_URL}/storage/{key}?op=…&exp=…&sig=…`.
```
u/{user_id}/p/{project_id}/docs/{document_id}/{safe_filename}         uploads (deleted with project)
u/{user_id}/p/{project_id}/dataset/v{n}/train.jsonl | eval.jsonl        approved dataset version
u/{user_id}/p/{project_id}/dataset/export-{ts}.jsonl                   ad-hoc JSONL export (TTL 1 day)
j/{job_id}/checkpoint/latest.zip                                        only latest; overwritten
j/{job_id}/adapter/adapter.zip                                          safetensors + config
j/{job_id}/adapter/adapter.gguf                                         converted by worker
j/{job_id}/eval/generations.jsonl                                       from notebook
```
- Pre-signed PUT: TTL 15 min (checkpoints 60 min), `Content-Type` fixed, `Content-Length` checked after upload via HEAD.
- Pre-signed GET: TTL 15 min.
- Lifecycle: `j/` objects deleted by cleanup task 14 days after job end; R2 lifecycle rule on `u/*/p/*/dataset/export-*` 1 day as backstop.
- CORS on bucket: `PUT, GET` from web origin only.

## 8. Configuration (env vars)

**API/workers (`backend/.env`)**
| Var | Purpose |
|---|---|
| `ENV` | local / staging / prod |
| `DATABASE_URL` | `postgresql+asyncpg://…` (Supabase session pooler) |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://…` for Celery/Alembic |
| `REDIS_URL` | `redis://redis:6379/0` |
| `SUPABASE_URL`, `SUPABASE_JWT_AUD` | JWT verification |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` | storage |
| `KEY_ENCRYPTION_KEYS` | comma-separated Fernet keys (first = current) |
| `WEB_ORIGIN` | CORS + email links |
| `PUBLIC_API_URL` | shown to notebook |
| `RESEND_API_KEY`, `EMAIL_FROM` | email |
| `SENTRY_DSN` | errors |
| `HF_TOKEN_READONLY` (optional) | higher HF API rate limit for model checks (no gated access) |
| `LLAMA_MODELS_DIR`, `LLAMA_SERVER_BIN` | playground |
| `NOTEBOOK_URL` | Colab link to the notebook on GitHub at the current tag |

**Frontend (`frontend/.env`)**: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SENTRY_DSN`. Nothing else (all `VITE_*` values are public).

## 9. Error model
- Domain exceptions in `core/errors.py`: `NotFound(404)`, `Forbidden(403)`, `Conflict(409)`, `InvalidTransition(409)`, `LimitExceeded(413/422)`, `ValidationFailed(422)`, `RateLimited(429)`, `UpstreamError(502)`, `TokenExpired(401, code=token_expired)`, `TokenRevoked(401, code=token_revoked)`.
- Body: `{"error": "<code>", "message": "<human text>", "details": {...}?}`. 422 from FastAPI validation reshaped to the same envelope with `details.fields`.
- Workers: unrecoverable → `transition(failed, reason=<code>, message=<human>)`; recoverable → retry with backoff.

## 10. Observability
- Structured JSON logs (`structlog`), request id middleware (`X-Request-ID`), user id and project id in context. Scrubber removes `authorization`, `api_key`, `token`, `ciphertext` fields.
- Sentry in web, API, workers; `before_send` scrubbing; traces sample 0.05.
- `/healthz` (process) and `/readyz` (DB + Redis) endpoints; Flower not exposed publicly.
- Free-tier usage dashboard (admin-only endpoint `/admin/usage`): DB size, R2 bytes, active jobs, emails sent today.

## 11. Training backend interface
```py
class TrainingBackend(Protocol):
    name: str
    def submit_job(self, db, project, dataset_version, model, preset) -> SubmitResult  # creates job (+ token for colab)
    def get_status(self, db, job) -> JobStatus                                      # derived from heartbeats
    def get_output(self, db, job) -> list[Artifact]
    def cancel(self, db, job) -> None                                               # revoke token, mark cancelled
```
`ColabBackend` is the only implementation in v1. `training_jobs.backend` stores `"colab"`. The services never reference Colab directly.
