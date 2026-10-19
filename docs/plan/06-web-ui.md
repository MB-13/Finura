# 06 — Web UI (React SPA, `frontend/`)

## 1. Setup
- **Vite + React 19 + TypeScript strict**, React Router (`createBrowserRouter`, lazy routes), Tailwind v4, shadcn/ui (CSS variables, neutral base + one brand accent), `lucide-react` icons, a small theme provider for dark mode.
- Libraries: `@tanstack/react-query` (+ devtools in dev), `openapi-fetch` + `openapi-typescript`, `@supabase/supabase-js` (+ `@supabase/ssr` if middleware is needed for redirects), `@microsoft/fetch-event-source`, `react-hook-form` + `zod` + `@hookform/resolvers`, `@tanstack/react-table` + `@tanstack/react-virtual` (review table), `recharts` (loss chart), `react-markdown` + `rehype-sanitize` (model output), `sonner` (toasts), `react-dropzone` (uploads).
- Deploy: `vite build` → static files in `dist/` → **Cloudflare Pages** at `doctune.pages.dev` (D10). `public/_redirects` has `/* /index.html 200` for SPA routing. No server code in `frontend/`. Auth guard (`<RequireAuth>`) runs client-side.
- Scripts: `dev`, `build`, `lint`, `typecheck`, `test` (Vitest), `test:e2e` (Playwright), `gen:api`.

## 2. Routes
| Route | Group | Purpose |
|---|---|---|
| `/` | (marketing) | Landing: what DocTune does, 4-step how-it-works, "it's free: you bring a free API key and your free Colab GPU", FAQ (fine-tuning vs RAG, Colab pauses), CTA |
| `/privacy`, `/terms` | (marketing) | Legal (third-party AI processing, Colab disclaimer) |
| `/docs/*` | (marketing) | Help: getting a free Groq key, running the notebook, resuming, using GGUF in Ollama |
| `/sign-in` | (auth) | Magic link + GitHub + Google |
| `/auth/callback` | (auth) | Supabase OAuth/magic-link callback |
| `/onboarding` | (app) | 3 steps: what to expect → connect an API key → create first project |
| `/projects` | (app) | Dashboard: project cards (name, status badge, step progress, updated), New project |
| `/projects/:id` | (app) | Project workspace — status-driven stepper (below) |
| `/projects/:id/dataset` | (app) | Full-screen review table (also reachable from stepper) |
| `/projects/:id/playground` | (app) | Chat playground |
| `/settings` | (app) | Tabs: API keys, Account (notifications, delete account) |

`(app)` layout: auth guard (client-side session check + redirect), top nav (logo, Projects, Settings, avatar menu, theme toggle), `QueryClientProvider`, toaster.

## 3. Project workspace (`/projects/:id`)
Left: vertical stepper **Upload → Style → Preview → Dataset → Train → Results**. Right: active panel chosen by `project.status` via exhaustive `switch`. Header: name (inline rename), status badge, overflow menu (activity, delete).

| Status | Panel | Key UI |
|---|---|---|
| `draft`, `uploaded` | **UploadPanel** | Dropzone (PDF in P1; +DOCX/TXT/MD in P2), per-file progress bars (XHR upload progress to R2), size meter "12.3 / 50 MB", file list with remove, "Process documents" button (enabled when ≥1 uploaded) |
| `parsing` | **ProcessingPanel** | Per-document status, pages, OCR count, live progress |
| `awaiting_style` | **StylePanel** + **PreviewResults** (if a preview exists) | Dataset format cards (Q&A / Instructions / Conversations, with relative quota cost and a sample example; ADR-0003) · Template picker cards · description textarea with examples of good descriptions · tone/length/format/language selects · examples editor (2–5 input/output pairs, add/remove) · warnings (single example, inconsistent) · Advanced: "Also add the description as a system prompt" · provider/model select (from connected keys) · "Generate preview" · after preview: pairs list with source excerpt + judge scores, "Looks good → Generate full dataset" (shows estimate dialog: requests, tokens, time, quota fit) or "Tweak style" |
| `previewing` | StylePanel (read-only) + skeleton preview | "Generating 8 sample pairs…" |
| `generating` | **GenerationPanel** | Progress (chunks done/total, pairs generated), current provider/model, notices (rate-limit switches), `waiting_quota` card with resume time and a tip ("Connect a Gemini key to finish faster"), Cancel. Multi-day runs are normal on Groq alone — copy says so up front |
| `in_review` | **ReviewPanel** | Stats (kept, train/eval, dropped by reason, avg scores), link to full table, Export JSONL, "Change style & regenerate", **Approve & continue** → **TrainSetupDialog** |
| (dialog) | **TrainSetupDialog** | Model cards (catalog; show mode "standard"/"memory-saving" instead of lora16/qlora4) + "Custom model" tab (HF id → check result with warnings/blocking, license ack checkbox) · preset cards with time hint · Advanced (collapsed) · Llama notice if applicable · "Create training job" |
| `awaiting_run` | **RunNotebookPanel** | Big steps: 1) copy job token (shown once; copy button; "regenerate" link) 2) **Open in Colab** button 3) Runtime → T4 GPU (screenshot) 4) Run all cells & keep tab open. Token expiry date. "Waiting for the notebook to connect…" live indicator. Cancel job |
| `training` | **TrainingPanel** | Progress % + step/max, ETA from step rate, live loss chart (metrics endpoint + SSE), GPU info, last heartbeat "12 s ago", "Keep the Colab tab open" tip, checkpoint info "Saved at step 340 · 4 min ago", Cancel |
| `paused` | **PausedPanel** | The design-doc message for the reason with %, "Open notebook again" button + token reminder (rotate if lost), download latest checkpoint, "Test current checkpoint in playground" (P5), loss chart so far |
| `evaluating` | **EvaluatingPanel** | "Running evaluation in your notebook…" |
| `ready` | **ResultsPanel** | Evaluation scores base vs tuned (bar chart; "scoring…" while pending), side-by-side samples, downloads (adapter.zip, adapter.gguf; where the GGUF / optional merged weights went: Drive path or HF repo), Ollama instructions, license/notice, **Open playground** |
| `failed` | **FailedPanel** | Message, Retry (if `allowed_actions` has it), activity log, contact/help link |

All panels use `allowed_actions` from the API to enable buttons.

## 4. Dataset review page
- Virtualized table (2,000+ rows incl. dropped): columns select · question · answer (labelled per dataset format: Instruction/Output, Opening question/Last answer with "+ N follow-ups") · split · scores · origin/edited · source (section path, hover excerpt).
- Filters: split (train/eval/all), kept/dropped (with reason), search, sort by score.
- Inline edit of the whole example in its format (instruction + optional input + output; conversation turns with add/remove follow-up) in the row expansion, keyboard: `j/k` move, `e` edit, `d` drop, `r` restore.
- Bulk: drop, restore, move to train/eval.
- Add pair dialog (fields follow the dataset format). Export JSONL offers the format's own layout too (Alpaca / ShareGPT). Optimistic updates with rollback on error.
- Read-only once approved (shows version).

## 5. Playground page
- Chat UI with streaming tokens, markdown rendering (sanitized), stop button.
- Toggles: RAG on/off (show sources under answers), "Compare with base model" (two columns), temperature slider, max tokens.
- Status bar: model warm/cold ("Loading your model… ~20 s"), source (final/checkpoint step N), CPU speed note for larger models + "Run locally with Ollama" link.
- History in component state (cleared on reload) — v1.

## 6. Settings — API keys
- Provider cards (Groq recommended badge, Gemini "speeds up generation", Cerebras marked "needs a payment method — optional"): status chip (valid/invalid/quota until hh:mm/unverified), masked key `gsk_…abcd`, default model select, priority (drag or up/down), Replace / Remove / Re-verify.
- "How to get a free key" links per provider (docs pages).
- Gemini: terms acknowledgement checkbox ("Google's terms restrict using outputs to build competing models"), EU/UK availability note.
- Key input is write-only (`type="password"`, never re-displayed).

## 7. Data layer
- `src/lib/api/client.ts`: `createClient<paths>({ baseUrl })` + middleware adding `Authorization` from the current Supabase session and mapping error envelopes to `ApiError {code, message, details}`.
- `src/lib/query-keys.ts`: `qk.project(id)`, `qk.projects()`, `qk.pairs(id, filters)`, …
- `src/lib/sse.ts` → `useProjectEvents(id)`: connects with fetch-event-source; on `snapshot`/`status` → `setQueryData(qk.project(id))`; on `progress`/`train_metrics` → dedicated caches; reconnect with backoff and token refresh; closes on unmount.
- Uploads: `useUploadDocument` → create → XHR PUT with progress → complete → invalidate.
- Errors: toast for mutations; inline for forms (422 `details.fields`); full-panel error with retry for queries.

## 8. Design system
Direction: calm, precise, modern SaaS (Linear / Vercel feel). Whitespace, subtle borders, soft shadows, one brand colour. Visual sandbox: `frontend/preview/README.md` (`pnpm preview:ui`, `/?view=gallery`).

**Tokens** (all in `src/index.css`, light + dark, oklch, wired through `@theme inline`; never use raw colours or `slate-*`/`blue-*` palette classes):
- shadcn names kept: `background foreground card popover primary secondary muted accent border input ring destructive chart-1..5 sidebar-*`. Brand = indigo-violet `primary` (~`oklch(0.52 0.22 277)`; lighter in dark with dark foreground). `accent` is a soft brand tint (hover/selected). `ring` is brand-tinted.
- Semantic status families `success`, `warning`, `info`, `destructive`, each with `-foreground` (text on the solid colour), `-muted` (soft background; also `bg-success/10` works) and `-muted-foreground` (text on the soft background, AA in both themes). Example: `bg-warning-muted text-warning-muted-foreground`.
- Status mapping (`components/status-meta.ts`): neutral = waiting, `info` = running, `warning` = paused, `success` = ready, `destructive` = failed.
- Radius `--radius: 0.75rem` (`rounded-md/lg/xl`); shadows `shadow-xs|sm|md|lg` (tinted, dark-mode aware). Focus: `focus-visible:ring-[3px] ring-ring/50` on controls, 2px outline on plain links.
- Dark mode: class-based. `ThemeProvider` (`components/theme/`) stores `light|dark|system` in `localStorage['doctune-theme']`; an inline script in `index.html` applies it before paint. Use `useTheme()` / `<ThemeToggle />`.

**Type** (self-hosted via fontsource: Inter Variable with the optical-size axis, `@fontsource-variable/inter/opsz.css`, so large text renders as Inter Display; Geist Mono Variable (OFL) is `font-mono`). Utilities: `text-display` (64/66 desktop, 40/44 mobile, 650, -0.035em; landing hero only) and `text-display-sm` (48/52; closing CTA, auth); `text-page-title` (28/36, 24 on mobile) one per page via `PageHeader`; `text-section-title` (18/28); `text-card-title` (15/22); `text-body` (15/24); `text-caption` (13/20, with `text-muted-foreground`); `text-eyebrow` (mono 11px uppercase, tracking 0.08em, muted; replaces the brand-coloured overline; `text-overline` is an alias, do not add `text-primary` to it); `text-metric` (mono + tabular numbers; add a size, e.g. `text-metric text-3xl`) for every stat, percentage, delta, count and timer. Tokens/ids/code: `font-mono`. Two-tone headlines: key phrase in `text-muted-foreground`.

**Dark palette** (near-black): background `oklch(0.155 0.01 277)`, card `0.185`, popover `0.205`, muted `0.22`, border `white/8%`, input `white/12%`, `--highlight: white/6%`. `shadow-card` (card elevation) = hairline shadow in light; in dark it adds an inset 1px top-edge highlight. Light border is slightly cooler (`oklch(0.92 0.006 277)`). Muted text is AA on card/background in both themes.

**Marketing / auth only** (never inside the app shell): `bg-dots`, `bg-grid` (faint patterns with a radial fade mask), `bg-glow` (brand glow from the top, `--glow` token, 12% light / 18% dark): put each on an `absolute inset-0 pointer-events-none` `aria-hidden` layer. `components/marketing/GuideRails.tsx`: `GuideRails` (centred `max-w-6xl` column with `border-x` rails) and `GuideJoint` (full-bleed hairline with "+" marks on the rails; place between sections, same width as the rails). `guide-plus` is the "+" utility.

**Flat surfaces**: `Stat` has `variant="tile"` (default) or `"inline"` (no box); `StatRow` (`items=[{label,value,hint?,icon?}]`) is one row of stats split by vertical hairlines, 2 columns on mobile. `AppFrame` (`title?`, `fade?`, `bodyClassName?`) is a framed app-window mock (three dots, border, `shadow-lg`, optional bottom fade) for hero/product visuals.

**Shared components** (`src/components/`): `PageHeader` (title, description, back, badge, actions), `Section`, `Stat`, `StatRow`, `AppFrame`, `KeyValue`, `Callout` (info/success/warning/destructive; icon + colour), `StatusBadge` (dot + label), `EmptyState`, `ErrorState`, `FullPageSpinner`, `NativeSelect`, `Logo`/`LogoMark`, `theme/ThemeToggle`, `layout/AppLayout` (sticky translucent header, nav, account menu with theme + Settings + Sign out), and `features/projects/ProjectStepper` (vertical rail on lg+, progress bar on mobile). shadcn `ui/*` gained `Badge` variants `success|warning|info`, `Progress indicatorClassName`, refined `Card` spacing.

**Usage rules**: compose from these before writing bespoke markup; one `<h1>` per page (`PageHeader`); content max width is set by the layout (`max-w-6xl`), pages do not add their own container padding; spacing rhythm `gap-6` between page blocks, `gap-8` between Sections, `gap-3/4` inside; cards for grouped content, no nested cards: inside one surface separate regions with `border-t`/`divide-x` hairlines and spacing, not inner tinted `bg-muted` boxes or bordered tiles (use `StatRow` / `Stat variant="inline"`, `KeyValue` rows); colour is never the only signal (icon/label too); every async view has skeleton, empty (with next action) and error (retry) states.
- Accessibility: all interactive elements keyboard reachable with visible focus, live regions for progress (`aria-live="polite"`), AA contrast in both themes (checked for every text/background token pair).
- Responsive: mobile first; stepper collapses to a progress bar; header fits at 360 px; review table becomes cards < 768px.
- Components still specific to features: `FileDropzone`, `UploadItem`, `ExamplesEditor`, `TemplatePicker`, `PairCard`, `ScoreChips`, `EstimateDialog`, `ModelCard`, `ModelCheckResult`, `PresetPicker`, `TokenReveal`, `ColabSteps`, `LossChart`, `ProgressWithEta`, `PauseNotice`, `EvalComparison`, `DownloadList`, `ChatMessage`, `SourcesList`, `ProviderKeyCard`.

## 9. Copy principles
Plain language, no ML jargon without a tooltip ("LoRA adapter — a small file with what your model learned"). Always tell users what happens next and what to do. Pauses are framed as normal ("Progress is saved").
