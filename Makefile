.PHONY: help up down logs migrate backend worker beat frontend test test-backend test-frontend test-notebook gen-api

COMPOSE = docker compose -f infra/docker-compose.dev.yml

help:            ## list targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

up:              ## start local services (postgres+pgvector, redis, mailpit)
	$(COMPOSE) up -d --wait

down:            ## stop local services
	$(COMPOSE) down

logs:            ## follow local service logs
	$(COMPOSE) logs -f

migrate:         ## apply database migrations
	cd backend && uv run alembic upgrade head

backend:         ## run the FastAPI dev server on :8000
	cd backend && uv run fastapi dev src/doctune/main.py --port 8000

worker:          ## run a Celery worker on all queues
	cd backend && uv run celery -A doctune.workers.celery_app worker -l info -Q parse,llm,embed,default,inference

beat:            ## run Celery beat
	cd backend && uv run celery -A doctune.workers.celery_app beat -l info

frontend:        ## run the Vite dev server on :5173
	cd frontend && pnpm dev

test: test-backend test-frontend test-notebook ## run all tests

test-backend:    ## backend lint, types and tests
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest

test-frontend:   ## frontend lint, types and tests
	cd frontend && pnpm lint && pnpm typecheck && pnpm test

test-notebook:   ## notebook package lint and tests (no GPU needed)
	cd notebook && uv run --extra dev ruff check . && uv run --extra dev pytest

gen-api:         ## regenerate frontend API types from the backend OpenAPI schema
	cd backend && uv run python -m doctune.openapi > ../frontend/openapi.json
	cd frontend && pnpm gen:api
