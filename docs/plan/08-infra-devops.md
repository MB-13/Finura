# 08 — Infrastructure & DevOps

Everything on free tiers. **Re-verify each limit when setting it up** (task T0.2) and record findings in `docs/runbooks/free-tiers.md`.

## 1. Accounts to create (T0.2)
| Service | Purpose | Notes |
|---|---|---|
| GitHub org `doctune` (check name) | Code, CI, hosts the notebook | Public repo needed for Colab "open from GitHub" (or a public `doctune-notebook` repo if the main repo stays private) |
| Supabase | Postgres + pgvector + Auth | Free: 500 MB DB, **2 active projects** (use for dev + prod), pause after 1 week inactivity — daily beat query as keep-alive |
| Cloudflare | Pages (static web), R2 | R2 free: 10 GB-month, 1M Class A / 10M Class B ops, free egress. Pages: static assets free |
| Oracle Cloud | Always Free ARM VM (**2 OCPU / 12 GB** since June 2026) | ARM capacity can be scarce — create it in week 1. Reclaimed only if 7-day p95 CPU, network **and** memory are all < 20%; our memory use stays above 20% |
| Resend | Email | Free 3,000/month, 100/day, 3 domains; real sending needs a verified domain → **the ~$10/yr domain is required for email**. Until then: in-app notices only |
| Sentry | Errors | Free developer plan |
| Groq (team test key) | Dev/testing only | Users bring their own keys in prod. Free: 200K tokens/day per model |
| Hugging Face | Optional read-only token for model checks | |

## 2. Local development (T0.4)
`infra/docker-compose.dev.yml`: `postgres` (pgvector image `pgvector/pgvector:pg16`), `redis`, `minio` (S3-compatible stand-in for R2, with bucket + CORS init), `mailpit` (catch emails), optional `llama` service.
- API: `uv run fastapi dev` on host; workers: `uv run celery … -Q parse,llm,embed,default,inference` (single dev worker).
- Web: `pnpm dev`; Supabase Auth: use a dev Supabase project (simplest) or Supabase CLI local stack (`supabase start`) — decide in T0.4 (recommend Supabase CLI so auth works offline).
- `make dev` / `justfile` with targets: `up`, `down`, `migrate`, `seed`, `backend`, `worker`, `frontend`, `test`, `gen-api`.
- Seed script: test user, sample PDF project in each status for UI development.

## 3. Production topology (Oracle VM)
`infra/docker-compose.yml` (all images `linux/arm64`):
| Service | Image | Notes |
|---|---|---|
| `caddy` | caddy:2 | TLS (Let's Encrypt) for `api.<domain>`; without a domain use a free DNS name (e.g. DuckDNS / sslip.io) — decide T0.6 |
| `api` | `ghcr.io/<org>/doctune-api` | uvicorn, 2 workers, mem 0.75 GB |
| `worker-parse` | same image | `celery -Q parse -c 1`, mem 2 GB, tesseract installed |
| `worker-llm` | same | `-Q llm -P threads -c 8`, mem 0.5 GB |
| `worker-cpu` | same | `-Q embed,default -c 2`, mem 1.5 GB |
| `worker-inference` | same + llama.cpp binaries | `-Q inference -c 1`, runs **one** llama-server; mem 4 GB |
| `beat` | same | single instance, 0.15 GB |
| `redis` | redis:7-alpine | AOF on, `maxmemory 256mb`, password, not exposed |

Total ≈ 9.2 GB of 12 GB (see `01 §1`), plus 4 GB swap.
- Only Caddy exposes ports (80/443). OCI security list + `ufw`: 22 (SSH, key-only, your IP), 80, 443.
- Dockerfile (API): multi-stage, `python:3.12-slim`, uv install, non-root user, tesseract-ocr + language packs (eng + a few), llama.cpp built for ARM (`GGML_NATIVE=ON`) in a separate stage for the inference image.
- Volumes: `redis-data`, `llama-models`, `adapter-cache`, `hf-cache`, `embed-model-cache`.
- Bootstrap script `infra/scripts/bootstrap-vm.sh`: Docker, swap 4 GB, unattended upgrades, fail2ban, ufw, create deploy user.

## 4. Web deploy
- `vite build` (static files in `dist/`, `_redirects` for SPA routing) → `wrangler pages deploy dist` to Cloudflare Pages (`doctune.pages.dev`) via GitHub Action on `main`. Public env vars are baked in at build time.
- Preview deployments per PR (Pages preview URLs) — add them to Supabase redirect URLs and API CORS via a wildcard for `*.doctune.pages.dev`.
- Workers free plan (10 ms CPU/request) is not used for the UI (D10).

## 5. R2 setup (T0.5)
- Bucket `doctune` (prod), `doctune-staging`. API token scoped to the bucket (Object Read & Write).
- CORS: origins = web URLs; methods PUT, GET, HEAD; headers `content-type`; max age 3600.
- Lifecycle rules: `dataset/export-` prefix 1 day (backstop; app cleanup handles `j/`).

## 6. Supabase setup (T0.3)
- Enable `vector` extension. Auth providers: email magic link, GitHub, Google; site URL + redirect URLs for local/staging/prod.
- Connection: session pooler URL for the async API (asyncpg with `statement_cache_size=0` if using transaction pooler); direct/session URL for Alembic.
- Email templates for magic link branded "DocTune". Supabase's built-in SMTP has very low rate limits → configure Resend SMTP for auth emails once a domain exists.
- Daily `pg_dump` backup (see §9).

## 7. CI/CD (GitHub Actions)
| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | PR + push | **backend**: uv sync, ruff, mypy, pytest (services: pgvector postgres, redis, minio) · **frontend**: pnpm install, lint, typecheck, vitest, build · **types-drift**: export OpenAPI, `gen:api`, `git diff --exit-code` · **notebook**: doctune_nb unit tests + CPU smoke (no-unsloth path) |
| `e2e.yml` | PR (label) + nightly | Compose stack + Playwright against fake LLM provider |
| `deploy-api.yml` | push to `main` (after CI) | build arm64 image (buildx/QEMU or ARM runner), push GHCR, SSH to VM: `docker compose pull && docker compose up -d`, run `alembic upgrade head` as a one-off (manual approval environment for prod) |
| `deploy-web.yml` | push to `main` | `vite build` + `wrangler pages deploy` |
| `notebook-release.yml` | tag `nb-v*` | build/test doctune_nb, update `NOTEBOOK_URL` / `notebook_min_version` config PR |
| `security.yml` | weekly | `pnpm audit`, `pip-audit`, gitleaks, CodeQL (free for public repos) |

Environments: Supabase free allows only 2 projects → **dev** (shared by developers + CI preview) and **prod**. No separate staging VM (12 GB is not enough for two stacks); staging = prod VM before public launch, then preview deploys of the web against the dev Supabase project.

## 8. Observability
- Sentry projects: web, api (includes workers). Release tagging with git sha. Alerts: new issue, error rate spike.
- Uptime: free uptime checker (e.g. Cloudflare health check / UptimeRobot free) on `/readyz` and web home.
- `usage_snapshot` beat task + `/admin/usage`.
- Log rotation: Docker `json-file` with `max-size=10m, max-file=5`.

## 9. Backups & recovery
- Nightly `pg_dump` (beat task on VM) → compressed → R2 `backups/` (keep 7 daily, 4 weekly). Monthly restore test into a local container (runbook).
- Redis: AOF, but treat as disposable — all task state is reconstructible from Postgres (runs resume via beat).
- Runbooks (`docs/runbooks/`): deploy, rollback, restore DB, rotate encryption key, rotate R2 credentials, VM rebuild from scratch, Supabase paused, R2 nearing quota, provider outage.

## 10. Encryption key management
- `KEY_ENCRYPTION_KEYS` = MultiFernet list. Rotation: prepend new key → deploy → run `rotate_provider_keys` task (re-encrypt with current) → remove old key after confirmation.
- Stored only in VM `.env` (600 perms) and a password manager. Never in GitHub secrets for anything but deploy SSH.
