# 11 — Task Breakdown

## Build status (2026-10-07)
All phases P0–P6 are implemented in code and pass their automated checks: backend 988 tests (ruff, mypy --strict,
migrations in sync), frontend 201 tests (oxlint zero warnings, tsc, Vite build), notebook package 89 tests. A live
run with real processes (API + Celery worker) completed create → upload (PDF + scanned PDF) → parse/OCR → chunks → delete.

**Not yet verified — needs your accounts or real hardware (do these next, in order):**
1. Supabase project (T0.3): real sign-in, JWT verification against the real JWKS.
2. A real Groq key: one preview + full generation with real models (prompt quality pass T2.15).
3. GitHub repo: push, CI green, set `NOTEBOOK_URL` and the org/`API_URL` placeholders in `notebook/doctune_train.ipynb`, tag `nb-v0.1.0`.
4. Colab release checklist on a real T4 (T3.12 / `docs/plan/10-testing.md` §6): Unsloth paths, Ctrl-C/pause/resume, batched eval, GGUF export to Drive, Ollama run.
5. Oracle VM (T0.6) + `infra/docker-compose.yml` + Caddy TLS; build the inference image; confirm llama.cpp generates with base GGUF + adapter GGUF (T5.5) and measure tokens/s (T5.6).
6. Cloudflare Pages deploy of `frontend/` (T0.12); then the launch checklist (`/launch-checklist`, P6 T6.8) incl. a lawyer review of the DRAFT privacy/terms pages.
7. Later (D20): switch storage from local disk to Cloudflare R2 (`R2Storage` with the same interface).

Format: **ID · Title** — owner agent · depends on · *design needed?*
Deliverables → Acceptance criteria (AC). Every task ends with `/ship-check`. Owners: `arch` system-architect, `be` backend-developer, `pipe` pipeline-engineer, `ml` ml-engineer, `db` database-engineer, `fe` frontend-developer, `ui` ui-designer, `qa` test-engineer, `ops` devops-engineer, `sec` security-auditor, `pm` product-strategist.

---

## P0 — Setup & scaffolding (≈1 week)

**Status 2026-10-07:** ✅ T0.1, T0.4, T0.7, T0.8, T0.9, T0.10, T0.11 done locally (backend 40 tests, frontend 18 tests, all lint/type checks green). ⏳ Waiting on accounts: T0.2, T0.3 (Supabase), T0.5 (deferred — local disk storage for now, D20), T0.6 (Oracle VM), T0.12 (deploy workflows written, switched off until secrets exist).
**Done when:** local stack runs with one command; CI green; signed-in web page shows `/me` from the API.

**T0.1 · Monorepo init** — ops · — ✅ (Makefile instead of justfile)
`git init`, `.gitignore`, `.editorconfig`, README, LICENSE choice (pm), `frontend/ backend/ notebook/ infra/ docs/`, `justfile`, pre-commit (ruff, prettier, gitleaks).
AC: `just --list` shows targets; pre-commit runs clean.

**T0.2 · Accounts & free-tier verification** — ops · —
Create the accounts in `08 §1`; record current limits with sources in `docs/runbooks/free-tiers.md`; flag anything that needs money (expected: domain for email).
AC: doc lists every service, limit, date checked, link.

**T0.3 · Supabase projects** — ops · T0.2
Dev + prod projects, `vector` extension, auth providers (magic link, GitHub, Google), redirect URLs.
AC: can sign in on a test page in dev; JWKS URL reachable.

**T0.4 · Local dev stack** — ops · T0.1 ✅ (Postgres+pgvector, Redis, Mailpit; no S3 container — D20)
`docker-compose.dev.yml` (pgvector, redis, minio + bucket/CORS init, mailpit), Supabase CLI local auth, `.env.example` files, seed script skeleton.
AC: `just up && just migrate && just api && just worker && just web` works on a clean machine; README "Getting started" verified.

**T0.5 · R2 buckets** — ops · T0.2
Buckets (staging/prod), scoped API tokens, CORS, lifecycle rule.
AC: pre-signed PUT from a browser on localhost succeeds for staging bucket.

**T0.6 · Oracle VM bootstrap (start day 1)** — ops · T0.2
Provision the ARM VM at the new free limit (**2 OCPU / 12 GB**; capacity may take days — retry regions), 4 GB swap, `bootstrap-vm.sh`, DNS name (free subdomain decision), Caddy TLS, Docker.
AC: `https://api.<host>/healthz` served by a placeholder container with valid TLS.

**T0.7 · API skeleton** — be · T0.4 ✅
uv project, FastAPI app factory, `core/config.py` (pydantic-settings), structlog JSON logging + request id, error envelope + handlers, `/healthz` `/readyz` `/meta`, CORS, Sentry init, async SQLAlchemy engine/session, Alembic configured, ruff/mypy/pytest config, Dockerfile (arm64 + amd64).
AC: `uv run pytest` passes health tests; `mypy --strict src` clean; Docker image builds for arm64.

**T0.8 · Celery skeleton** — pipe · T0.7 ✅
`celery_app.py`, queues, beat, `task_db()`, `publish()` stub, a `ping` task, worker services in compose.
AC: `ping.delay()` result returned in dev; beat triggers a heartbeat log task.

**T0.9 · Auth dependency + users** — be + db · T0.3, T0.7 ✅ (verified with test JWKS; real Supabase pending T0.3)
Migration `0001_init` (users, enums incl. project_status, project_events, email_log); `current_user` with JWKS; user upsert; `GET/PATCH /me`.
AC: tests with test-JWKS: valid → 200; expired/wrong aud/alg none → 401; first request creates user row.

**T0.10 · Web skeleton** — fe · T0.4 ✅ (React + Vite; real sign-in pending T0.3)
Vite + React + TypeScript app, React Router, Tailwind, shadcn init, theme, layouts, Supabase client, sign-in page (magic link + OAuth), auth callback, `<RequireAuth>` guard, QueryClient, `openapi-fetch` client + `gen:api` script, a `/projects` placeholder showing `/me`.
AC: sign in locally → see your email from the API; `pnpm build` produces static files in `dist/`; deploys to Cloudflare Pages.

**T0.11 · CI** — ops · T0.7, T0.10 ✅ (runs once the repo is on GitHub)
`ci.yml` (api, web, types-drift, notebook placeholder), Dependabot, `security.yml`.
AC: PR shows all checks green; deliberate type drift fails CI.

**T0.12 · Deploy pipelines (staging)** — ops · T0.6, T0.11
`deploy-api.yml` (GHCR arm64, SSH compose up, migrations), `deploy-web.yml` (`vite build` → Pages).
AC: merge to main deploys both; the deployed web signs in and calls the VM API.

---

## P1 — Foundation (≈2 weeks)
**Done when:** an uploaded PDF shows its chunks, with live status over SSE, on staging.

**T1.1 · Projects model & transitions service** — db + be · T0.9 · *design: arch reviews ALLOWED table*
Projects table, `services/projects.transition()` with full ALLOWED table (all phases), `project_events`, `allowed_actions()` computation.
AC: table-driven test of every (from,to,actor); concurrent transition test (FOR UPDATE) passes.

**T1.2 · Projects API** — be · T1.1
`GET/POST/PATCH/DELETE /projects`, `GET /projects/{id}` (ProjectOut with counts, allowed_actions), `/activity`, limit 20 active projects.
AC: authz matrix (alice/bob) passes; OpenAPI regenerated.

**T1.3 · Storage** — be · T0.7 ✅ (done early in P0)
`core/storage.py`: `Storage` interface + `LocalStorage` (disk, HMAC-signed expiring URLs served by `/storage/*`). `R2Storage` (boto3) added later with the same methods (D20).
AC: tests for signed upload/download, tampering, expiry, size cap, content type, path traversal ✅.

**T1.4 · Documents upload API** — be · T1.2, T1.3
`documents` table, create (pre-signed PUT), complete (HEAD + magic-byte sniff), list, delete; caps 20/50 MB; PDF only; `draft→uploaded`.
AC: tests for oversize (413), wrong type (415), size mismatch → object deleted, other user (404), cap across files.

**T1.5 · SSE events** — be · T0.8, T1.2
`core/events.py` (Redis pub/sub, sync + async), `GET /projects/{id}/events` with sse-starlette, snapshot on connect, keep-alive.
AC: test publishes from a worker context and receives on the stream; unauthorized stream 404.

**T1.6 · PDF parsing & chunking** — pipe · T0.8, T1.4
`parsing/pdf.py` (pymupdf4llm), `ocr.py` (tesseract), cleaning, `chunker.py`, `parse_document` task, `on_doc_done` transition, `POST /process`, `GET /chunks`.
AC: fixtures — text PDF → chunks with section paths, 300–1,000 tokens; scanned PDF → OCR text; encrypted → doc failed with message; all-failed → project failed; re-run idempotent.

**T1.7 · Embeddings** — pipe · T1.6
`chunks.embedding` column usage, e5-small encoder, `embed_chunks` task on `embed` queue (model cached in a volume).
AC: all chunks embedded after parse; second run no-ops; memory < 2 GB.

**T1.8 · Dashboard UI** — fe + ui · T1.2, T0.10
`/projects` cards, New project dialog, empty state, StatusBadge, delete with confirm.
AC: component tests per state; responsive; a11y check (axe) clean.

**T1.9 · Workspace shell + stepper + SSE hook** — fe · T1.5
`/projects/:id` page, `ProjectStepper`, exhaustive status switch with placeholder panels, `useProjectEvents`.
AC: changing status via API updates the UI live without refresh; adding a status to the union without a panel fails typecheck.

**T1.10 · Upload & processing panels** — fe + ui · T1.4, T1.6, T1.9
Dropzone, XHR progress, size meter, process button, ProcessingPanel, chunk viewer (section path, page, text).
AC: E2E journey 1 passes against compose stack.

**T1.11 · Deploy parse/embed workers to VM** — ops · T1.6, T1.7, T0.12
Compose services with memory limits, tesseract packages, model cache volume.
AC: staging demo: upload 10 MB PDF → chunks visible < 2 min.

**T1.12 · Phase review** — sec + qa · all P1
Security review of auth/uploads/R2; test gaps filled.
AC: no Critical/High open.

---

## P2 — Dataset generation (≈3 weeks)
**Done when:** a user approves a dataset they like on staging.

**T2.1 · Provider keys** — be + db · T1.2
`provider_keys` table, `core/crypto.py` (MultiFernet), `/keys` CRUD, `verify_key` task, masked output, Gemini terms ack, priority.
AC: ciphertext in DB; no key in logs (log-capture test); verify marks valid/invalid with fake provider.

**T2.2 · Keys settings UI** — fe + ui · T2.1
Provider cards, write-only input, status chips, priority, help links + docs page "Get a free Groq key".
AC: component tests; key never re-displayed.

**T2.3 · LLM client & providers** — pipe · T2.1 · *design: re-verify model IDs/limits (baseline in `docs/runbooks/free-tiers.md`)*
`llm/providers.py` with per-**model** specs (rpm/rpd/tpm/tpd), `client.py` (request + token-per-minute buckets, retry-after, (provider, model) fallback chain, quota flags per model, JSON mode, repair retry), `ProvidersExhausted`.
AC: fake-provider tests for ok, 429 → next model, daily quota on one Groq model → next Groq model, invalid key, broken JSON → repair, all exhausted → exception with retry_after. Real smoke test: the gen and judge prompts return valid JSON on all three Groq models.

**T2.4 · Style model & templates** — db + be · T1.2
`style_templates` (seed: support_bot, tech_docs_assistant, json_extractor, faq_bot, tutor), `style_configs` (immutable, hash), `PUT/GET /style`, example warnings (heuristics), `/style-templates`.
AC: tests: templates prefill; editing creates new row; warnings for 1 example and inconsistent formats.

**T2.5 · Style UI** — fe + ui · T2.4
StylePanel: template picker, description, selects, ExamplesEditor (2–5), advanced toggle, provider/model selector, warnings.
AC: form validation mirrors API; 422 field errors displayed.

**T2.6 · Preview generation** — pipe + be · T2.3, T2.4
`generation_runs`, `dataset_pairs`, prompt `gen-v1`, `generate_preview` (+ judge on preview), `POST /preview`, `GET /runs/{id}`, `/runs/{id}/pairs`; transitions previewing↔awaiting_style.
AC: preview returns ~8 pairs with source excerpts within 60 s on Groq free tier; preview failure returns to awaiting_style with message.

**T2.7 · Preview UI** — fe + ui · T2.6, T2.5
PreviewResults with PairCard, scores, "tweak" loop, re-preview.
AC: loop works repeatedly; stale preview (style changed) clearly marked.

**T2.8 · Estimate** — be · T2.3
`GET /estimate`, EstimateDialog.
AC: numbers match the formula in `04 §7`; fits_daily_quota flag correct for fixtures.

**T2.9 · Full generation fan-out** — pipe · T2.6
`start_full_run`, `generate_chunk` (idempotent results table, per-user semaphore), counter-based completion, `waiting_quota` + `resume_waiting_runs` beat, cancel.
AC: 200-chunk fixture completes with fake provider; killing a worker mid-run and restarting completes without duplicates; quota exhaustion → waiting_quota → auto-resume.

**T2.10 · Judge, dedupe, trim, split (finalize)** — pipe · T2.9, T1.7
`judge-v1`, `judge_batch`, `finalize_run`, embedding dedupe, trim to target with coverage balance, 90/10 split; `generating→in_review`; dataset_ready email.
AC: deterministic with seed; dropped reasons recorded; counts in ProjectOut correct.

**T2.11 · Generation progress UI** — fe · T2.9
GenerationPanel with progress, provider notices, waiting_quota card, cancel.
AC: live updates via SSE; cancel returns to style.

**T2.12 · Review API** — be · T2.10
`/pairs` list/filter/sort/search, PATCH, POST, bulk, `/dataset/stats`, `/dataset/export`, `/dataset/approve` (dataset_versions + JSONL to R2), `/dataset/restyle`.
AC: approve validates 50 ≤ kept ≤ 2000 and eval ≥ 5; JSONL validates against chat format schema; read-only after approve.

**T2.13 · Review UI** — fe + ui · T2.12
ReviewPanel + full review table (virtualized, inline edit, bulk, keyboard, add pair), export, approve.
AC: 2,000 rows scroll at 60 fps; optimistic edit rollback on error; E2E journey 2 passes.

**T2.14 · More file types** — pipe · T1.6
DOCX (mammoth), TXT, MD parsers; extend allow-list and sniffing.
AC: fixtures parsed with headings preserved.

**T2.15 · Prompt quality pass** — pm + pipe · T2.10
Run real generation on 3 sample document sets × 3 templates; review pair quality; tune prompts (`gen-v2` if needed) and judge thresholds; record results in `docs/adr/`.
AC: ≥ 80% of kept pairs rated acceptable in manual review of 50 samples per set.

**T2.16 · Phase review** — sec + qa.

---

## P3 — Colab training (≈2–3 weeks)
**Done when:** one model trains end to end from the notebook on a real Colab T4; project `ready` with adapter in R2.

**T3.0 · Colab spike** — ml · — ✅ **DONE 2026-10-07 (ADR-0001)**
Per `05 §10`: Qwen3.5 4B 16-bit LoRA in fp16 vs Qwen3 4B QLoRA vs Qwen3 8B QLoRA on a free T4.
AC: ADR-0001 with step time, kernel-compile time, VRAM, stability (no NaN), checkpoint size, upload time, GGUF export time/size, adapter→GGUF load in llama.cpp; **D16 default model decided**.

**T3.1 · Model catalog & HF check** — ml + be · T3.0
`catalog.py` with verified HF IDs and `train_mode` per model (D15), `hf_check.py` (mode selection + size limits per mode), `/models/catalog`, `/models/check`, Unsloth supported-architecture list verified.
AC: tests with recorded HF API responses: apache ok, gated warning, unsupported arch blocked, >10B blocked, unknown license warning, Llama flagged.

**T3.2 · Presets** — ml · T3.0
`presets.py`, `/training/presets`, max_steps computation, time hints **per token** (spike used 88-token examples: Qwen3.5 4B 3.0 s/step, Qwen3 4B 2.1 s, Qwen3 8B 5.0 s) plus ~8 min per-session startup for Qwen3.5 (kernel compile + load). Re-measure step time with ~400-token examples during T3.6.
AC: unit tests for step math and large-model overrides.

**T3.3 · Training jobs & tokens** — db + be · T2.12, T3.1
Tables (`training_jobs`, `job_tokens`, `training_metrics`, `checkpoints`, `artifacts`), `ColabBackend` (TrainingBackend protocol), `POST /training` (in_review→awaiting_run, token once), token rotate, cancel, `current_job` dependency.
AC: token stored hashed; expired/revoked/other-job tests; cancel revokes and returns to in_review.

**T3.4 · Notebook endpoints** — be · T3.3
`/jobs/current/config|start|heartbeat|training-complete|artifacts/*|finish|fail|pause` (checkpoint endpoints in P4), metrics sampling, SSE `train_metrics`, notebook version check (426).
AC: fake notebook drives a full happy path in pytest; project statuses move awaiting_run→training→evaluating→ready.

**T3.5 · `doctune_nb` package: api client, env, data** — ml · T3.4
Client with retries/friendly errors, GPU detection, dataset download + sha verify + chat template.
AC: unit tests with respx fake API.

**T3.6 · `doctune_nb` train + heartbeat callback** — ml · T3.5
Unsloth model load per `train_mode` (qlora4 / lora16, fp16), non-thinking chat template, LoRA, SFTTrainer, responses-only, heartbeat callback, cancel_requested handling, OOM handling.
AC: CPU smoke (no-unsloth path) trains 5 steps against fake API; on Colab T4 trains the D16 default model on 300 pairs.

**T3.7 · Adapter upload & finish (no eval yet)** — ml · T3.6
Save adapter → zip → upload → complete → finish.
AC: adapter.zip in R2; project ready; artifacts listed.

**T3.8 · Notebook file** — ml + pm · T3.7
`doctune_train.ipynb` cells per `05 §4.2`, clear markdown copy, tag `nb-v0.1.0`, `NOTEBOOK_URL`.
AC: a non-ML teammate completes a run following only the notebook + UI.

**T3.9 · Train setup UI** — fe + ui · T3.1, T3.2, T3.3
TrainSetupDialog: model cards, custom model check, license ack, presets, advanced, Llama notice.
AC: blocking results disable submit; license ack required for non-permissive.

**T3.10 · Run notebook & training UI** — fe + ui · T3.4, T3.9
RunNotebookPanel (TokenReveal, ColabSteps, waiting indicator), TrainingPanel (progress, ETA, LossChart, heartbeat age), basic ResultsPanel with adapter download.
AC: E2E journey 3 (happy path part) with fake notebook passes.

**T3.11 · Emails v1** — be · T3.4
Resend integration, `send_email` with dedupe, templates `training_finished`, `dataset_ready`, `job_failed`; Mailpit in dev.
AC: emails captured in Mailpit tests; opt-out respected.

**T3.12 · Colab release checklist (partial)** — ml + qa · T3.8
Run `10 §6` items applicable to P3, including the large-model VRAM test.
AC: results recorded; catalog `fits_t4` updated for Qwen3 8B.

**T3.13 · Phase review** — sec (job tokens!) + qa.

---

## P4 — Checkpoint & resume (≈1–2 weeks)
**Done when:** killing the Colab runtime mid-training leads to `paused` + email, and re-running continues from the checkpoint to `ready`.

**T4.1 · Checkpoint endpoints** — be · T3.4
`/jobs/current/checkpoint/latest|upload-url|complete`, single latest object, size limit, sha.
AC: tests: replace older checkpoint; mismatched size rejected.

**T4.2 · Checkpoint callbacks** — ml · T4.1
TimedCheckpointCallback (7 min), UploadCheckpointCallback (zip, PUT with retries, complete), save_total_limit=1.
AC: CPU smoke shows uploads at intervals; upload failure retried and doesn't crash training.

**T4.3 · Resume path** — ml · T4.2
Download + verify + `resume_from_checkpoint`; `start(resumed_from_step)`; dataset sha & lib version checks.
AC: smoke: train 10 steps → kill → resume continues at saved step with identical subsequent loss (seeded) on CPU path; Colab manual test passes.

**T4.4 · Pause handling** — be + pipe · T3.4
`/jobs/current/pause`, `monitor_heartbeats` beat, reasons, `paused→training` on heartbeat/start, emails `paused`/`resumed`, `token_expiring`.
AC: accelerated-time test: silence → paused + one email (dedupe); resume → training.

**T4.5 · Paused UI** — fe + ui · T4.4
PausedPanel with design-doc messages, reopen notebook, token rotate, checkpoint download.
AC: each reason renders correct copy with %; E2E journey 3 full passes.

**T4.6 · Graceful stop** — ml · T4.2
KeyboardInterrupt / cancel_requested → save + upload checkpoint → pause(user_stopped).
AC: interrupting the train cell leaves a resumable checkpoint.

**T4.7 · Colab release checklist (resume items)** — ml + qa.

**T4.8 · Phase review** — sec + qa.

---

## P5 — Delivery (≈2–3 weeks)
**Done when:** a ready project shows evaluation scores, downloadable artifacts, and a working playground with RAG.

**T5.1 · Notebook evaluation** — ml · T3.7
`evaluate.py` (tuned vs base with disabled adapter, ROUGE-L, generations upload).
AC: generations.jsonl schema valid; ≤ 10 min for 100 items on T4 (4B).

**T5.2 · Evaluation scoring** — pipe + be · T5.1, T2.3
`evaluations` table, `score_evaluation` task (`eval-judge-v1`), `/evaluation`.
AC: fake provider test; no key → failed with message, notebook metrics still shown.

**T5.3 · Export in notebook** — ml · T3.7
GGUF Q4_K_M to Drive or HF (default), opt-in merged 16-bit (≤ 4B to Drive, > 4B HF only), Drive free-space and RAM checks, README/Modelfile with the correct non-thinking chat template, license/NOTICE, Llama naming.
AC: GGUF runs in Ollama locally with correct template; a full Drive produces a clear skip message, not a crash; Llama custom model output named and noticed correctly.

**T5.4 · Results UI** — fe + ui · T5.2, T5.3
EvalComparison chart, samples, DownloadList, export locations, Ollama instructions.
AC: scoring pending state; component tests.

**T5.5 · Adapter → GGUF conversion** — ml + pipe · T3.7
llama.cpp in inference image, base config cache, `convert_adapter_to_gguf` (final + checkpoint sources). Conversion itself already verified in Colab (42.5 MB, `qwen35` tag).
AC: on the Oracle VM, base `Qwen3.5-4B-Q4_K_M.gguf` + converted adapter **generates text** in llama-server, output differs from base and shows the trained style; tokens/s recorded. If LoRA-on-CPU is too slow (llama.cpp falls back from CPU_REPACK for LoRA tensors), switch the playground to merged GGUFs (ADR).

**T5.6 · Inference manager** — ml + be · T5.5
`inference/manager.py` (single warm process, FIFO queue, idle shutdown, health wait, defer while parsing), `ensure_loaded` task, base GGUF download script.
AC: on the 2 OCPU / 12 GB VM: swap between two users' models works; process stays < 4 GB; measured tokens/s recorded in the ADR and shown in UI copy.

**T5.7 · RAG + chat endpoint** — be · T5.6, T1.7
`inference/rag.py`, `/playground/status|warmup|chat` (SSE proxy, sources event, limits, compare-base).
AC: streamed tokens reach the client; sources returned; rate limits enforced.

**T5.8 · Playground UI** — fe + ui · T5.7
Chat, streaming, stop, RAG toggle, sources, compare mode, warm-up state, CPU note.
AC: E2E journey 4 passes with stub server.

**T5.9 · Per-request LoRA investigation** — ml · T5.6 · *design*
Check whether the deployed llama.cpp supports per-request adapter selection; ADR; implement if it reduces RAM.
AC: ADR written.

**T5.10 · Phase review** — sec (playground XSS, limits) + qa.

---

## P6 — Hardening & launch (≈1–2 weeks)
**Done when:** `12-launch.md` checklist all ✅ and production is live.

**T6.1 · Account deletion & retention** — be + pipe — `DELETE /me`, `purge_project`, `cleanup_retention`. AC: tests verify DB + R2 empty for the user.
**T6.2 · Rate limits everywhere** — be — slowapi rules per `09`. AC: tests for 429s.
**T6.3 · Onboarding & docs pages** — pm + fe + ui — onboarding flow, `/docs/*` help, landing page, FAQ (fine-tuning vs RAG). AC: new user reaches a preview without outside help (hallway test).
**T6.4 · Legal pages** — pm — privacy (third-party AI processing, R2/Supabase storage, retention), terms (Colab disclaimer, user responsibility for provider terms & model licenses). AC: linked in footer and sign-up.
**T6.5 · Full security review** — sec — `09` table. AC: no Critical/High.
**T6.6 · Load sanity & free-tier projections** — qa + ops — k6, usage projection for 100 users. AC: report in `docs/runbooks/`.
**T6.7 · Production environment** — ops — prod Supabase/R2/compose, backups, alerts, runbooks. AC: restore test done.
**T6.8 · Launch checklist** — run `/launch-checklist`. AC: all items ✅ with evidence.
**T6.9 · Accessibility & UX polish pass** — ui. AC: axe clean on all pages; keyboard-only run of journey 1–3.

---

## Kaggle automatic training (ADR-0002)
**K1 · Kaggle backend (be)** — done: `compute_accounts` + `training_jobs.{launch_attempts, external_ref, external_url}` (migration 0005); `training/kaggle_client.py` (httpx, Bearer `KGAT_` / Basic legacy); `training/kaggle_kernel.py` (embedded notebook package); `KaggleBackend` + `get_backend`; tasks `check_kaggle_account`, `launch_kaggle_job`, `poll_kaggle_jobs` (beat, 2 min); `/compute/kaggle` endpoints; `backend` on `POST /projects/{id}/training`. AC: tests with a mocked Kaggle API cover client, kernel source, launch, relaunch/fail paths, cancel revokes tokens.
**K2 · Kaggle UI (fe)** — Settings card (connect/check/disconnect, GPU hours), backend choice in the training panel, Kaggle states in the progress panel. AC: Playwright journey with mocked API.
**K3 · Live Kaggle verification (ops)** — end-to-end run on a real account through the deployed API; confirm `SaveKernel` title/slug handling and quota field formats. AC: runbook entry.

## Dataset formats (ADR-0003)
**F1 · Phase 1: Q&A, instructions, conversations (be + fe)** — done: migration 0006 (`style_configs.dataset_format`, `dataset_pairs.{dataset_format, record}`, `dataset_versions.dataset_format`); `services/formats.py`; per-format generation prompts and judge rubrics; `GET /dataset-formats`; `record` on pairs (PATCH/POST); `shape` on export (Alpaca / ShareGPT); conversation context in evaluation scoring; format picker on the Style step, per-format preview cards, review table and add dialog. AC: `tests/test_dataset_formats.py`, Vitest for picker and editors.
**F2 · GPU check (ml)** — train a small conversation dataset on Qwen3.5 4B and Qwen3 4B; decode the labels to confirm only assistant turns are trained, and that llama.cpp renders the same template. AC: note in ADR-0003.
**F3 · Playground "Input" box for instruction projects (fe + be)** — optional second field so a task and its text are sent like the training data. Not built yet.
**F4 · Phase 2a prompt–completion, 2b preference (DPO)** — see ADR-0003 "Not now"; DPO starts with a T4 memory spike.

---

## P7 — Growth (post-launch backlog, prioritized by pm)
- Saved user style profiles (`user_style_profiles`, save/load in StylePanel)
- More base models + custom-model playground (server-side base GGUF conversion)
- "Train again" (ready → awaiting_run) and multiple jobs per project with comparison
- Additional training backends via the TrainingBackend interface (Lightning AI, local GPU; Kaggle if terms allow)
- Paid GPU backend + Stripe billing
- Docling parser option for complex PDFs; more languages for OCR
- Persisted playground history; shareable demo links
- Teams/orgs
