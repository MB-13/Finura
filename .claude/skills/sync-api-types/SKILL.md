---
name: sync-api-types
description: Regenerate the web app's typed API client from FastAPI's OpenAPI schema and fix any resulting TypeScript errors. Use after any change to FastAPI routes or Pydantic schemas.
---

# Sync API types

1. Export the schema without a running server:
   `cd backend && uv run python -c "import json; from doctune.main import app; print(json.dumps(app.openapi()))" > ../frontend/openapi.json`
2. Generate types: `cd frontend && pnpm gen:api` (runs `openapi-typescript openapi.json -o src/lib/api/schema.d.ts`).
3. `pnpm typecheck` — fix call sites broken by the contract change (don't loosen types with `any` or casts).
4. Check the diff of `schema.d.ts` for unintended changes (renamed fields, missing `response_model`, `Any` types).
5. Report what changed in the contract.

Never hand-edit `src/lib/api/schema.d.ts`.
