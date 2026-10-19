# DocTune — Implementation Plan

Date: 2026-10-07 (rev. 2 — free-tier limits and model support verified, see §5 and `docs/runbooks/free-tiers.md`) · Source: `docs/design/doctune-design.md` · Status: **Draft — awaiting approval of the decisions in §4**

This plan covers everything needed to take DocTune from an empty repo to launch. It is split into files so each agent can read only what it needs:

| File | Contents |
|---|---|
| `00-overview.md` | This file: goals, phases, timeline, decisions needing approval, how to execute |
| `01-architecture.md` | Components, repo layout, auth, status machine, SSE, R2 layout, env vars, error model |
| `02-data-model.md` | Every table, column, enum, index and retention rule |
| `03-api-contract.md` | Every HTTP endpoint (web + notebook), request/response, auth, errors |
| `04-pipeline.md` | Celery queues and tasks: parsing, chunking, generation, judge, dedupe, split, embedding, monitor, cleanup |
| `05-training-notebook.md` | Model catalog, custom model checks, presets, notebook cells, checkpoint/resume, eval, export |
| `06-web-ui.md` | Routes, screens per status, components, state, UX copy |
| `07-playground.md` | llama.cpp inference manager, adapter conversion, RAG, streaming |
| `08-infra-devops.md` | Accounts, Oracle VM, docker compose, Cloudflare, R2, Supabase, CI/CD, monitoring, backups |
| `09-security.md` | Threat model and controls |
| `10-testing.md` | Test strategy per layer, fixtures, CI gates |
| `11-tasks.md` | **Ticket-level task list** for every phase with owner agent, dependencies, acceptance criteria |
| `12-launch.md` | Launch checklist, legal pages, post-launch |

---

## 1. Goal
A user with no ML knowledge can: sign up → upload documents → describe a style → preview and generate a dataset with their own free LLM key → review it → train a QLoRA model on their own free Colab T4 (with pause/resume) → evaluate → download adapter/merged/GGUF → chat with it (with RAG) in the browser. Every component is free.

## 2. Phases (from the design-doc roadmap, plus setup and launch)

| Phase | Name | Done when | Est.* |
|---|---|---|---|
| P0 | Setup & scaffolding | Repo, accounts, CI, local dev stack all green; "hello" page calls API with a Supabase-authenticated request | 1 wk |
| P1 | Foundation | An uploaded PDF shows its chunks; status updates live over SSE | 2 wk |
| P2 | Dataset generation | A user approves a dataset they like (preview loop, full run, judge, dedupe, review table, JSONL export) | 3 wk |
| P3 | Colab training | One model trains end to end from the notebook; adapter in R2; project `ready` (the T3.0 spike can start in week 1) | 2–3 wk |
| P4 | Checkpoint & resume | Kill the Colab runtime mid-training → project `paused` + email → rerun → continues from the checkpoint and finishes | 1–2 wk |
| P5 | Delivery | Playground with RAG, evaluation scores, GGUF/merged export, downloads | 2–3 wk |
| P6 | Hardening & launch | Security review, legal pages, launch checklist all ✅, deployed on `doctune.pages.dev` | 1–2 wk |
| P7 | Growth (post-launch) | More file types/models, saved style profiles, paid GPU backend, Stripe | ongoing |

\*Rough estimate for 1–2 developers working with Claude agents. Total to launch: **~12–16 weeks**.

Build rule from the design doc: **build the end-to-end path once with one file type (PDF) and one model (the D16 default), then widen.** DOCX/TXT/MD and more models come in P2/P5 only after the PDF path works.

## 3. Critical path
```
P0 scaffolding ─► P1 auth+upload+parse+SSE ─► P2 style+preview+generation+review ─► P3 job token+notebook+train ─► P4 checkpoint/resume ─► P5 playground+eval+export ─► P6 launch
                                   └─► P1 infra on Oracle VM (parallel) ─────────────────────────────────────────────────┘
```
Parallelizable work: infra (P0–P1 in parallel with app code), UI polish behind API contracts. **De-risking first:** the Colab spike (T3.0) is ✅ done; Oracle VM provisioning (T0.6) starts in week 1 because capacity can take days.

## 4. Decisions this plan makes that the design doc doesn't (need your approval)

| # | Decision | Why | Alternative |
|---|---|---|---|
| D1 | Add a `draft` project status before `uploaded` | A project exists before any file is uploaded | Create the project only at first upload |
| D2 | After a preview finishes, status returns to `awaiting_style` with the preview attached (no separate "preview_ready" status) | Keeps the doc's 12 statuses; the preview loop is "edit style ↔ preview" | Add `preview_ready` status |
| D3 | Provider quota exhaustion during generation does **not** use project `paused`; the generation run gets state `waiting_quota`, project stays `generating` | `paused` in the doc is training-specific with Colab messages | Reuse `paused` with a generation reason |
| D4 | Add cancel edges: `awaiting_run/training/paused → in_review` (revokes job token) | Users need to change base model or abort | No cancel in MVP |
| D5 | **The notebook is generic, not generated per job.** One notebook on GitHub; the job token carries everything (config, dataset URL) | Nothing per-user lives on GitHub; simpler | Generate a per-job .ipynb |
| D6 | Eval split: the notebook generates base & tuned answers for ≤100 eval items and uploads them; a **worker** scores them with the user's LLM key via the judge. Project goes `ready` when the notebook finishes; scores appear when scoring completes | The notebook must not receive the user's LLM API key | Score with cheap metrics only inside the notebook |
| D7 | Playground serves **base GGUF + LoRA adapter converted to GGUF** with llama.cpp `--lora`, conversion done by a worker on the VM. Only curated base models get playground support in v1 | Merged GGUFs stay in the user's Drive per the doc; adapters are small and fit R2 | Upload full GGUF to R2 (breaks storage caps) |
| D8 | Embeddings for RAG + dedupe: `intfloat/multilingual-e5-small` (384-dim) on the VM CPU via sentence-transformers | Free, multilingual (the style form has a language option), runs on ARM | Gemini embeddings (needs user key, not EU/UK) |
| D9 | PDF parsing with **PyMuPDF4LLM** (markdown with headings) + **Tesseract OCR** for low-text pages; DOCX via `mammoth`→markdown; Docling kept as an optional later upgrade | Docling is heavy/slow on a shared CPU VM; PyMuPDF is fast | Docling first |
| D10 | Frontend: **React single-page app (Vite + React Router)**, static files on **Cloudflare Pages** at `doctune.pages.dev`; backend: FastAPI (your decision, 2026-10-07) | UI-only frontend needs no server rendering; Workers free plan allows only 10 ms CPU/request anyway | Next.js |
| D11 | SSE from the browser uses `@microsoft/fetch-event-source` so the Supabase JWT goes in the `Authorization` header (native `EventSource` can't send headers) | No tokens in URLs/logs | One-time SSE ticket in the query string |
| D12 | Python: SQLAlchemy 2.0 async + Alembic own the `public` schema; Supabase is used as plain Postgres + Auth. No Supabase client/RLS in the API (service connection) — RLS enabled with deny-all as defense in depth | One migration system, testable locally | Supabase migrations + RLS as primary authz |
| D13 | Default dataset size: target **500** kept pairs (max 2,000), overgenerate ×1.3 to absorb filtering | Groq free = 200K tokens/day **per model**; 500 pairs ≈ 550K tokens incl. judging ≈ one day across 3 Groq models. Larger targets show a multi-day estimate | 1,000 default (≈2 days on Groq) |
| D14 | Rate limiting with `slowapi` on Redis; per-user generation concurrency 1 project at a time | Free tiers + fair use | No limit in MVP |
| D15 | **Two training modes by model family:** Qwen3.5 (0.8B/2B/4B) → **16-bit LoRA** in fp16 (Unsloth advises against QLoRA for Qwen3.5); Qwen3 (0.6B–8B) → **4-bit QLoRA**. Qwen3.5 9B is **dropped** (needs ~22 GB) | Verified Unsloth guidance; T4 = 16 GB | QLoRA everywhere (lower quality on Qwen3.5) |
| D16 | ✅ **Resolved by the Colab spike (ADR-0001): default = Qwen3.5 4B, 16-bit LoRA in fp16.** Stable on T4, 9.7 GB VRAM, 1.42× slower per step than Qwen3 4B QLoRA, better factual answers. Qwen3 4B QLoRA = "faster" option + fallback. Qwen3 8B QLoRA fits (8.3 GB) | Measured on a free T4 | Qwen3 4B QLoRA default |
| D17 | **Exports:** adapter → DocTune R2 first (project becomes `ready`), then optional **GGUF Q4_K_M** (2.8 GB for 4B, ~22 min) to Drive or HF. Merged 16-bit (9.3 GB for 4B) → user's **HF account only**, opt-in. 8B: adapter-only by default; GGUF/merged experimental | Measured: 4B GGUF export peaked at 10.1 of 13.6 GB Colab RAM; merged 4B = 9.3 GB vs 15 GB free Drive | Always export merged to Drive |
| D18 | **Generation provider rotation is per model, not just per provider:** Groq limits are per model, so the chain is e.g. `groq/gpt-oss-120b → groq/qwen3.8-27b → groq/gpt-oss-20b → gemini/flash`. Cerebras is listed as optional (now needs a card; credits expire) | Verified limits | Provider-level fallback only (⅓ of the free quota) |
| D19 | **Server sized for Oracle's new 2 OCPU / 12 GB free limit:** one warm playground model at a time (queue others), smaller worker pools, OCR limited to 1 job at a time | Oracle halved Always Free A1 in June 2026 | Second free VM elsewhere (none comparable) |
| D20 | **Local disk storage for now** behind a `Storage` interface; uploads/downloads use HMAC-signed, expiring URLs served by the API (same flow as R2 pre-signed URLs). Switch to Cloudflare R2 later by adding `R2Storage` + config — no other code changes | Your decision (2026-10-07); no cloud account needed to build P1–P2 | R2 from day one |

If you disagree with any of these, change it here first; the other plan files follow these decisions.

## 5. What the verification changed (2026-10-07)
- **Groq is ~5× tighter than the design doc assumed** (200K tokens/day per model, 8K tokens/min). Datasets take longer; D13 + D18 compensate. Users with a Gemini key generate much faster.
- **Cerebras is no longer free** (card required, $5 credits expiring in 30 days).
- **Oracle free VM is now 2 OCPU / 12 GB** (D19). Playground serves one model at a time at ~3–6 tokens/s for a 4B model.
- **Qwen3.5 should not use QLoRA**; 9B doesn't fit a T4 (D15). The doc's "Qwen3.5 9B fits with QLoRA" is withdrawn.
- **Colab spike passed (ADR-0001):** Qwen3.5 4B trains stably in fp16; checkpoint/resume is exact (0.07% loss difference); adapter → GGUF conversion tags `qwen35` correctly; GGUF and merged exports work. Costs to design for: ~6 min kernel compile + ~2 min load per Qwen3.5 session (also on every resume) and ~22 min GGUF export. llama.cpp generation with the adapter is confirmed on the Oracle VM in T5.5 (in Colab it loaded but was killed for lack of RAM).
- **Cloudflare Workers free CPU limit (10 ms)** rules out server rendering → static React SPA on Pages (D10). (My earlier concern about the 3 MB size limit was outdated — that limit no longer applies; the CPU limit is the real blocker.)
- **Exports** default to adapter + GGUF (D17).
- **Supabase free allows 2 projects** → dev + prod; local auth via Supabase CLI.
- **Email needs a domain** (Resend) → budget ~$10/yr, or ship without email at first and show pause notices in-app only.

## 6. How to execute with Claude
1. Approve/adjust §4.
2. For each phase in `11-tasks.md`, in order: `/plan-feature <task-id>` only where the task says *needs design*, otherwise `/new-feature <task-id>`.
3. Each task names its owner agent; run independent tasks of a phase in parallel.
4. End every task with `/ship-check`; end every phase with the phase's "Done when" demo and `security-auditor` on the phase diff.
5. Keep this plan current: when a decision changes, edit the plan file in the same PR.

## 7. Out of scope for v1 (explicit)
Privacy features beyond the policy statement (per the design doc) · Kaggle/Lightning/local GPU backends (interface ready, not implemented) · paid GPU backend · Stripe · teams/orgs · saved style profiles beyond built-in templates (P7) · custom-model playground · mobile app · i18n of the UI (dataset language option is supported).
