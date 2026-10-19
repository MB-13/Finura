# 10 — Testing Strategy

## 1. Pyramid
| Layer | Tool | Scope | Runs |
|---|---|---|---|
| API unit | pytest | services (transitions table, caps, estimates, presets, hf_check parsing), crypto, chunker, prompt rendering | every PR |
| API integration | pytest + httpx `AsyncClient` + real Postgres (pgvector) + Redis + MinIO | every route: success / 422 / 401 / other-user 404 / invalid transition 409 / caps | every PR |
| Workers | pytest, Celery `task_always_eager` for unit + real worker for a few integration tests | parse fixtures, generation with fake providers, finalize (judge/dedupe/split), monitor, cleanup, purge | every PR |
| Notebook | pytest on `doctune_nb` with a fake API (respx) + CPU tiny-model smoke (no-unsloth path) | client retries/errors, checkpoint zip/upload/resume, heartbeat throttling, eval file format | every PR |
| Notebook GPU | manual on Colab T4, scripted checklist | full train/resume/export per catalog model | per notebook release |
| Web unit/component | Vitest + RTL + MSW (mock API from OpenAPI types) | each panel per status, forms, review table interactions, SSE hook | every PR |
| E2E | Playwright against docker-compose stack + fake LLM provider + fake notebook script | journeys below | label + nightly |
| Load sanity | k6 (local) | 50 concurrent SSE connections, heartbeat endpoint 10 rps | before launch |

## 2. Key fixtures
- Users: `alice`, `bob` (authz), JWT factory signing with a test JWKS.
- Docs: `text.pdf` (headings), `scanned.pdf` (2 pages image-only), `encrypted.pdf`, `empty.pdf`, `big-pages.pdf` (600 pages, generated), `manual.docx`, `notes.md`, `utf16.txt`.
- Fake LLM provider (respx router) with modes: `ok`, `rate_limited(n)`, `daily_quota`, `invalid_key`, `broken_json`, `slow`.
- Fake notebook (`tests/fake_notebook.py`): drives `/jobs/current/*` (start, heartbeats, checkpoint upload, stop silently, resume, finish) — used in API tests and E2E.

## 3. Critical E2E journeys
1. Sign in (Supabase test user) → create project → upload PDF → process → see chunks.
2. Connect key (fake provider) → style from template → preview → tweak → full generation → review (edit, drop, add) → approve.
3. Create training job → token shown → fake notebook connects → training progress chart updates → fake notebook goes silent → monitor (accelerated: 15 min → 5 s in test config) → paused panel + email in Mailpit → fake notebook resumes → finish → ready with downloads.
4. Playground: with a stub inference server (tiny model or fake streaming) → message streams, sources shown.
5. Authz: Bob can't open Alice's project URL (404 page).
6. Delete project → gone, R2 objects gone (MinIO check).

## 4. Status machine test
Table-driven test generates every (from, to, actor) triple; asserts allowed iff in `ALLOWED`; also asserts every status has a UI panel (web test enumerates the TypeScript union).

## 5. Gates
- PR merge requires: CI green, `code-reviewer` no Blockers, types-drift clean.
- Coverage targets (not hard gates): services ≥ 90%, routers ≥ 85%, workers ≥ 80%, web features ≥ 70%.
- Phase exit requires its E2E journey passing + manual demo of the "Done when".

## 6. Manual Colab release checklist (per `nb-v*`)
- [ ] Fresh Colab, T4: default model (D16) Balanced on 300 pairs completes; adapter in R2; project ready
- [ ] Interrupt runtime at ~30% → paused after 15 min → rerun → resumes at saved step, loss continuous
- [ ] Disconnect & delete runtime → rerun → resumes from R2 checkpoint
- [ ] No-GPU runtime → clear message, project paused(no_gpu)
- [ ] Revoked token → clear message
- [ ] GGUF export to Drive, loads in Ollama locally
- [ ] Llama custom model (gated) with user HF token → naming + license files correct
- [ ] Large model (Qwen3 8B QLoRA) VRAM peak recorded
