---
name: frontend-conventions
description: Conventions for DocTune's React web app (frontend/) - Vite + React + TypeScript SPA, UI-only role, folder structure, React Router, typed API client, TanStack Query, SSE, Supabase Auth, status-driven screens, uploads to R2, styling. Load whenever writing or reviewing code under frontend/.
user-invocable: false
---

# frontend/ conventions

## Role
The frontend is a **React single-page app** (Vite + React + TypeScript), built to static files and deployed to Cloudflare Pages. It is **UI only**: no DB access, no business logic, no secrets. FastAPI is the single source of truth.

## Stack
Vite · React 19 · TypeScript strict · React Router (`createBrowserRouter`, lazy routes) · TanStack Query · `openapi-fetch` + generated `schema.d.ts` · Tailwind CSS v4 · shadcn/ui · `@supabase/supabase-js` · `@microsoft/fetch-event-source` · react-hook-form + zod · Vitest + React Testing Library · Playwright · pnpm.

## Structure
```
frontend/src/
  main.tsx              entry: providers (QueryClient, theme, auth) + RouterProvider
  router.tsx            all routes; app routes wrapped in <RequireAuth>
  routes/               one file per page (thin: reads params, composes feature components)
  features/<feature>/   components/, api.ts (query/mutation hooks), hooks/, types.ts
                        features: auth, projects, documents, style, dataset, training, playground, settings, models
  components/ui/        shadcn primitives
  components/           shared app components (StatusBadge, EmptyState, ErrorState, …)
  lib/api/              schema.d.ts (generated — never hand-edit), client.ts, errors.ts
  lib/                  supabase.ts, sse.ts, query-keys.ts, env.ts, utils.ts
```
Names: components `PascalCase.tsx`, hooks `useX.ts`, others `kebab-case.ts`. Alias `@/*` → `src/*`.

## Routes
`/` landing · `/sign-in` · `/auth/callback` · `/onboarding` · `/projects` · `/projects/:id` · `/projects/:id/dataset` · `/projects/:id/playground` · `/settings` · `/privacy` · `/terms` · `/docs/*`.
`public/_redirects` contains `/* /index.html 200` so Cloudflare Pages serves the SPA for every path.

## Data
- All calls through the generated client in `lib/api/client.ts`; never hand-write request/response types.
- TanStack Query for server state; keys from `lib/query-keys.ts`; invalidate after mutations.
- SSE (`/projects/{id}/events`) via `fetch-event-source` (so the JWT goes in the `Authorization` header); one shared hook writes into the query cache and reconnects with backoff.
- The Supabase access token is attached as `Authorization: Bearer` by client middleware.

## Project screen
`/projects/:id` renders a stepper; the active panel is chosen by `project.status`:
`draft/uploaded` → upload · `parsing` → processing · `awaiting_style` → style form (+ preview results) · `previewing` → preview loading · `generating` → progress · `in_review` → review · `awaiting_run` → Open-in-Colab + job token · `training` → live loss chart · `paused` → reason + resume instructions · `evaluating` → progress · `ready` → results, downloads, playground · `failed` → message + retry.
Use an exhaustive `switch` so a new status is a type error. Enable buttons from the API's `allowed_actions`, never by re-implementing the state machine.

## Uploads & secrets
- Request a pre-signed URL from the API, PUT directly to R2 (XHR for progress), then confirm with the API. Pre-check 20 MB/file, 50 MB/project.
- Job tokens are shown once with a copy button; API keys are write-only inputs; display masked values only.
- Env vars: only `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SENTRY_DSN` — everything with `VITE_` ships to the browser, so never put a secret there. Read them only through `lib/env.ts`.

## Rendering
Render model output as text/markdown with `react-markdown` + `rehype-sanitize` — never `dangerouslySetInnerHTML`. Lazy-load heavy pages (review table, playground, charts).

## Quality
TypeScript strict, no `any`. Every async view: skeleton, empty, error. Accessible, responsive, dark mode.
