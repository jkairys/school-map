# oth-admin

Local-only React SPA admin UI for the OTH scraper service.

## Stack

- React 19 + Vite 7
- Tailwind CSS 4 (`@tailwindcss/vite`)
- Lucide React icons
- react-router-dom v7
- Plain JS + JSX (no TypeScript) — consistent with `apps/frontend/`

## Dev workflow

```bash
# From apps/oth-admin/

# Install dependencies (first time)
npm install
# or: task install

# Start Vite dev server (proxies API calls to localhost:8000)
npm run dev
# or: task dev
# Open http://localhost:5173/admin/

# Lint
npm run lint
# or: task lint

# Production build — compiles bundle and copies into services/oth-scraper/static/admin/
task build
```

The FastAPI service must be running on port 8000 for the dev server proxy to work.

## Production

`task build` runs `vite build` and rsyncs `dist/` into
`services/oth-scraper/static/admin/`. FastAPI mounts that directory at `/admin/`
via `StaticFiles(html=True)`. The mount is conditional on the directory existing,
so the backend still starts cleanly if the SPA hasn't been built yet.

## API path choice — no `/api` prefix

The SPA calls backend paths **without** an `/api` prefix, e.g.:

```js
fetch('/scrape-lists')          // GET all areas
fetch('/scrape-lists/1/summary')  // GET area summary
```

**Rationale**: the existing FastAPI routers already live at the root (`/scrape-lists`,
`/jobs`, etc.). Adding an `/api` prefix would require updating every existing test,
the Typer CLI's `api_client.py`, and all curl examples in the README. The simpler
path is to leave the API at root and serve the SPA at `/admin/`. The Vite dev proxy
maps each API path prefix individually to `http://localhost:8000`, so `fetch()` calls
are identical between dev and prod.

## Routes

| Path | Component | Status |
|---|---|---|
| `/admin/` | redirect → `/admin/areas` | done |
| `/admin/areas` | Areas dashboard | done (slice 07) |
| `/admin/areas/:id` | Area detail | stub — slice 08 |
| `/admin/suburbs/:id` | Suburb detail | planned — slice 10 |
| `/admin/properties/:id` | Property detail | planned — slice 11 |
| `/admin/listings/:id` | Listing detail | planned — slice 11 |
| `/admin/runs/:id` | Run detail | planned — slice 12 |

## Shared components

| Component | Location | Purpose |
|---|---|---|
| `StatCard` | `src/components/StatCard.jsx` | Labelled number tile |
| `RunStatusPill` | `src/components/RunStatusPill.jsx` | Coloured status pill (running/succeeded/partial/failed) |
| `CategorySplit` | `src/components/CategorySplit.jsx` | For-sale / For-rent / Sold count badges |
| `Layout` | `src/components/Layout.jsx` | App shell with top-bar |

## API clients

| Module | Location | Exports |
|---|---|---|
| `areas.js` | `src/api/areas.js` | `listAreas()`, `getAreaSummary(id)` |
