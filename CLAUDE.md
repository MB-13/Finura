# DocTune

Users upload documents, describe how they want a model to respond, and get back a QLoRA fine-tuned open-source model — no ML knowledge needed. DocTune generates the training dataset from their documents, the user trains it on **their own free Google Colab T4** via a notebook we provide, and DocTune delivers weights (adapter / merged / GGUF) plus a chat playground with RAG.

**Source of truth:** `docs/design/doctune-design.md` (what & why; converted from `DocTune — Project Design Document.docx`) and `docs/plan/` (how: architecture, data model, API contract, pipeline, notebook, UI, infra, security, testing; tickets in `docs/plan/11-tasks.md`). Read the relevant section before designing or building anything. If code and the design doc disagree, ask — don't silently pick one.

**Hard constraint: everything must be free** (free tiers or open source). Any new dependency or service must have a free tier that fits; flag anything that costs money.

## Architecture
```
Browser ──► frontend/ React SPA (Vite, UI only, static files on Cloudflare Pages)
               │  typed fetch + SSE
               ▼
           backend/ FastAPI (Oracle Cloud Always Free ARM VM)
               ├─► Supabase Postgres + pgvector
               ├─► Cloudflare R2 (pre-signed URLs only)
               └─► Redis ──► Celery workers (parse, generate, judge, embed, heartbeat monitor)
                              llama.cpp server (playground, CPU)

Colab notebook (user's Google account) ──► FastAPI /jobs/current/* (job token)
                                       ──► R2 (pre-signed PUT/GET)
```
- **The React frontend is UI only.** No database access, no business logic, no secrets. It calls FastAPI and renders.
- **FastAPI never does slow work.** A request writes a record, enqueues a Celery task, and returns. Workers do parsing, LLM calls, judging, embedding.
- **One project status field drives the UI** (see below). Only the listed actor may move each status.
- **Training is pluggable** behind one interface: `submit_job`, `get_status`, `get_output`, `cancel`. Backends: Kaggle (automatic, default when connected) and the Colab notebook (manual fallback).

## Project status machine
Full transition table: `docs/plan/01-architecture.md §5`.

| Status | Moved by |
|---|---|
| `draft` | API (project created, no files yet) |
| `uploaded` → `parsing` | API → parse worker |
| `awaiting_style` | user |
| `previewing` → `generating` | generation worker |
| `in_review` → `awaiting_run` | user |
| `training` | notebook heartbeat (job token) |
| `paused` | notebook, or heartbeat monitor after 15 min silence (store reason, email user) |
| `evaluating` → `ready` | notebook |
| `failed` | any worker (store message) |
| cancel: `awaiting_run/training/paused` → `in_review` | user (revokes job token) |

Transitions go through one service function that validates the from→to edge; never assign `status` directly.

## Stack
| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript strict, React Router, Tailwind + shadcn/ui, TanStack Query, `openapi-typescript` client generated from FastAPI, pnpm |
| Backend | FastAPI (see API row) |
| API | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + Alembic, Python 3.12, uv, ruff, mypy |
| Auth | Supabase Auth in the browser; FastAPI verifies the Supabase JWT. Notebook uses a per-job token (hashed in DB, 14-day expiry, revocable) |
| DB | Supabase Postgres + pgvector |
| Queue | Celery + Redis (self-hosted on the Oracle VM), Celery beat for the heartbeat monitor |
| Storage | Cloudflare R2 via pre-signed URLs |
| Parsing | Docling or PyMuPDF (+ OCR) |
| Generation | User's own API key (Groq default, rotating its 3 open models; Gemini recommended as a second key; Cerebras optional — needs a card) through one OpenAI-compatible client with a (provider, model) fallback chain |
| Training | Unsloth + TRL/PEFT, **fp16** (T4 has no bf16). Default **Qwen3.5 4B, 16-bit LoRA** (ADR-0001); Qwen3 → 4-bit QLoRA |
| Playground | llama.cpp (GGUF) on VM CPU + RAG over pgvector |
| Realtime | Server-Sent Events |
| Server | Oracle Always Free ARM: **2 OCPU / 12 GB** — one warm playground model |
| Email / monitoring | Resend · Sentry · Weights & Biases |

## Repo layout
```
frontend/               React SPA (Vite)
  src/routes/           one file per page; src/router.tsx defines routes
  src/features/<f>/     components, hooks, api calls per feature
  src/components/ui/    shadcn primitives
  src/lib/api/          generated OpenAPI types + client (never hand-edit schema.d.ts)
backend/
  src/doctune/
    main.py
    core/               config, db, auth, r2, crypto, email
    models/             SQLAlchemy models
    schemas/            Pydantic request/response models
    routers/            projects, documents, styles, datasets, jobs (notebook), playground, settings
    services/           business logic (status transitions live here)
    llm/                OpenAI-compatible client, provider fallback, prompts
    training/           training backend interface + colab backend
    workers/            celery_app.py, tasks/{parse,generate,judge,embed,monitor}.py
  alembic/  tests/
notebook/               doctune_train.ipynb + train.py template (Unsloth)
infra/                  docker-compose for the Oracle VM (api, worker, beat, redis, llama.cpp)
docs/design  docs/prd  docs/adr  docs/ideas
```

## Non-negotiables
- Users' LLM API keys are **encrypted at rest** and **never logged** or returned to the browser in full.
- DocTune **never stores Google credentials or HF tokens**; those are entered in the notebook via `getpass`.
- The **Colab** notebook stays **interactive**: user runs cells, one job per notebook, no headless runs, no web UI served from Colab (Colab free-tier rules). The **Kaggle** backend runs automatically through Kaggle's official API, always in the **user's own** Kaggle account (token encrypted like LLM keys; ADR-0002).
- Limits: 20 MB/file, 50 MB/project, 2,000 training pairs. R2 holds only adapters + the latest checkpoint per job, deleted 14 days after job end.
- Dataset generation always runs a cheap **preview** first; full run only after user approval.
- Custom base models are validated via the HF API (Unsloth-supported arch, ≤ ~10B, license check with warning, gated → user's own HF token).

## Commands
- Frontend (`frontend/`): `pnpm dev` · `pnpm lint` · `pnpm typecheck` · `pnpm test` · `pnpm build` · `pnpm gen:api`
- Backend (`backend/`): `uv run fastapi dev src/doctune/main.py` · `uv run ruff check . && uv run ruff format --check .` · `uv run mypy src` · `uv run pytest` · `uv run alembic upgrade head`
- Worker: `uv run celery -A doctune.workers.celery_app worker -l info` (+ `beat`)
- Notebook (`notebook/`): `uv run --extra dev pytest` · everything at once: `make test`

## Working with Claude here
Agents in `.claude/agents/`, skills in `.claude/skills/`. Flow: `/plan-feature` → `/new-feature` → `/write-tests` → `/ship-check`. Conventions per area: `frontend-conventions`, `backend-conventions`, `ml-conventions`.
