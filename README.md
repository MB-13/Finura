# DocTune

Upload documents, describe the style you want, and get a fine-tuned open-source model — trained for free on your own Google Colab GPU.

- Design: [`docs/design/doctune-design.md`](docs/design/doctune-design.md)
- Implementation plan: [`docs/plan/`](docs/plan/00-overview.md) (tasks in [`11-tasks.md`](docs/plan/11-tasks.md))
- Decisions: [`docs/adr/`](docs/adr/)

## Layout
| Folder | What |
|---|---|
| `frontend/` | React SPA (Vite, TypeScript, React Router, TanStack Query, Tailwind, shadcn/ui) |
| `backend/` | FastAPI API + Celery workers (Python 3.12, uv, SQLAlchemy, Alembic) |
| `notebook/` | Colab training notebook + `doctune_nb` package (and the T4 spike) |
| `infra/` | docker-compose files and server scripts |

## Getting started
Requirements: Docker, [uv](https://docs.astral.sh/uv/), Node 22 with corepack (`corepack enable`).

```bash
make up                                   # Postgres (pgvector), Redis, Mailpit on 5xxxx ports
cp backend/env.example backend/.env       # then set SUPABASE_URL
cp frontend/env.example frontend/.env     # then set VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
cd backend && uv sync && cd ..
cd frontend && pnpm install && cd ..
make migrate
make backend      # http://localhost:8000  (docs at /docs)
make worker       # Celery worker (separate terminal)
make frontend     # http://localhost:5173
```
Sign-in needs a Supabase project (free): Authentication → URL configuration → add `http://localhost:5173/auth/callback` as a redirect URL.

Files are stored on local disk for now (`backend/.data/storage`); Cloudflare R2 comes later behind the same storage interface.

## Status
All phases are implemented and tested in code. What still needs real accounts/hardware is listed at the top of
[`docs/plan/11-tasks.md`](docs/plan/11-tasks.md).

## Production
`infra/docker-compose.yml` (Oracle ARM VM, Caddy TLS), `infra/env.example`, `infra/scripts/bootstrap-vm.sh`,
`infra/scripts/backup.sh`; frontend deploys to Cloudflare Pages. Guide: [`docs/runbooks/oracle-vm-setup.md`](docs/runbooks/oracle-vm-setup.md).

## Checks
```bash
make test            # backend: ruff, mypy, pytest · frontend: lint, typecheck, vitest · notebook: ruff, pytest
make gen-api         # regenerate frontend API types after backend API changes
```
Local services: Mailpit (caught emails) at http://localhost:58025.
