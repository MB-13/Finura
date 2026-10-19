# UI preview harness (dev only)

Renders any real page/panel with fixture data and a stubbed `fetch`: no backend, no Supabase.
It is a separate Vite entry, excluded from `pnpm build`, `pnpm lint` and the app `tsconfig`.

## Run
```bash
pnpm preview:ui            # http://localhost:5174
pnpm typecheck:preview     # type-check the harness + fixtures
```

URLs (all state is in the query string, so screenshots are reproducible):

| URL | Shows |
|---|---|
| `/` | index of every scenario |
| `/?view=gallery` | design-system gallery (tokens, type, components) |
| `/?scenario=workspace-training` | real route from `src/router.tsx` with stubbed API |
| `&theme=dark` / `light` / `system` | theme (default light) |
| `&route=/projects/<id>/dataset` | override the scenario's route |

Scenarios exist for the projects list (empty/loading/error), the workspace in **all 13 statuses**
(`workspace-<status>`, plus loading / not-found), dataset, playground, settings, onboarding, landing, sign-in, docs.

## Add a page fixture
1. Open `scenarios.ts`. Default API data (`defaultHandlers`) already covers most endpoints; reuse the factories from
   `src/test/fixtures.ts` (`makeProject`, `makePair`, `makeJob`, ...) or `projectFor(status, overrides)`.
2. Add an entry to `scenarios`:
   ```ts
   'dataset-empty': {
     route: `/projects/${PROJECT_ID}/dataset`,
     note: 'Review table with no pairs',
     handlers: [(url) => (url.pathname.endsWith('/pairs') ? json({ items: [], next_cursor: null }) : undefined)],
   },
   ```
   Handlers listed on the scenario win over defaults. `json(body, status)` builds a response; `pending()` never resolves
   (loading/skeleton state); return a `{ error, message }` body with status 4xx/5xx for error states.
3. Missing endpoint? The page shows an error state and the stub returns 404 with the path, so you can see what to add.

## Screenshot
```bash
preview/shot.sh <scenario|gallery> <out.png> [width=1440] [height=900] [theme=light]
preview/shot.sh workspace-paused /tmp/shots/paused.png                 # desktop
preview/shot.sh workspace-paused /tmp/shots/paused-m.png 390 844       # mobile
preview/shot.sh workspace-paused /tmp/shots/paused-dark.png 1440 900 dark
```
Uses headless Chrome (`/usr/bin/google-chrome`, override with `CHROME=`). Screenshots are viewport-sized: raise the
height for long pages. Then open the PNG and look at it. Check light, dark, and 390 px wide (and 360 px for the header).
