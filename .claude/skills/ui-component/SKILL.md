---
name: ui-component
description: Build a DocTune UI component or screen in frontend/ with Tailwind + shadcn/ui - wired to FastAPI via the generated client and TanStack Query, status-aware, accessible, responsive, with loading/empty/error states. Use when creating or restyling components, forms, tables, dialogs or project-flow screens.
argument-hint: "[component or screen]"
---

# UI component

Target: $ARGUMENTS. Load `frontend-conventions`.

1. Reuse `src/components/ui/` (shadcn); add missing primitives with `pnpm dlx shadcn@latest add <name>`.
2. Place it: feature-specific → `src/features/<feature>/components/`; shared → `src/components/`.
3. Data: query/mutation hooks in `src/features/<feature>/api.ts` using the generated client; never call `fetch` with hand-written URLs/types.
4. If it depends on project state, branch on `project.status` explicitly and handle every relevant status (incl. `paused` with reason and `failed` with message).
5. Live updates: subscribe through the shared SSE hook, update the query cache.
6. Forms: react-hook-form + Zod mirroring the API schema; show server 422 field errors; pending state.
7. States: skeleton, empty (with next action), error (retry).
8. Accessibility & responsiveness: semantic elements, labels, focus, keyboard, contrast, mobile-first, dark mode.

Delegate polish to **ui-designer**.
