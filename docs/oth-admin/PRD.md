# PRD — OTH admin UI

## Problem Statement

The OTH scraper service captures rich time-series data about Australian residential listings (areas of suburbs, scrape runs, properties, listings, listing snapshots, price history), but today every interaction with that data goes through SQL, the FastAPI Swagger page, or the `oth` Typer CLI. I cannot tell at a glance which of my areas are alive and producing data, when each area was last scraped, what came back, or which suburbs are stale. Routine admin chores — kicking off a run, retrying a single failed `(suburb, category)` job after an anti-bot block, adding a new suburb to an area, editing filters — all require dropping to the CLI or hand-crafting JSON in Swagger. None of the latent value in the snapshot history is visible: no price-over-time chart, no per-suburb medians, no re-listing detection. The service has a working pipeline but no operator surface.

## Solution

A local-only single-page React app at `apps/oth-admin/`, served from the existing FastAPI service at `/admin/`, with five primary routes mapped to the existing domain entities:

- `/areas` — dashboard listing every area (the user-facing label for `scrape_list`) with its latest run status, suburb count, properties observed, and active-listing splits.
- `/areas/:id` — area detail: filters, list of suburbs (each as a stat card), an expandable Past Runs log, and Run-now / Edit / Add-suburb actions.
- `/suburbs/:id` — suburb detail: per-category 3×2 New/Changed grid anchored to the last completed scrape window, totals per category, three medians (sold last-30d, asking, rent), and a paginated property table.
- `/properties/:id` — property detail: every listing campaign ever attached to this address with first/last seen, status, latest snapshot summary.
- `/listings/:id` — listing detail: price-history chart from snapshot data, snapshot table, raw payload viewer.
- `/runs/:id` — run detail: per-job table grouped by `(suburb, category)` with retry buttons on failed/dead-letter rows.

Behind the UI, the service grows three structural additions: a first-class `scrape_run` entity to replace ad-hoc "fanout = jobs sharing a timestamp" inference; aggregate summary endpoints (`/scrape-lists/{id}/summary`, `/suburbs/{id}/summary`) that pack everything one screen needs into a single response; and an extracted `listing.sale_date` column populated by the reconciler from OTH's `raw_payload`. The producer is widened to accept narrowed `(suburb_ids, categories)` runs, and a new `/scrape-runs/{id}/retry-failed` endpoint re-enqueues the failed jobs of a previous run as a new run with `trigger_source='retry'`. A new `/suburbs/autocomplete?q=` endpoint feeds a live picker for the add-suburb flow.

Refresh is adaptive: each page loads with one summary fetch and, if the latest run is in flight, begins polling every 5 seconds until it terminates. Binding stays 127.0.0.1, no auth, matching the scraper PRD. The dev DB will be reset as part of this work — no backfill required.

## User Stories

1. As an operator, I want to open `/areas` and see every area at a glance with its latest run status, so that I can tell within five seconds which areas are healthy and which are stale.
2. As an operator, I want each area card to show "properties observed", "active listings" split into for-sale / for-rent / sold, and the timestamp of the last triggered run, so that I have a one-screen pulse of the data I'm collecting.
3. As an operator, I want areas to be labelled "Area" in the UI even though the backend calls them `scrape_list`, so that the language matches how I think about the data.
4. As an operator, I want to click into an area and see its suburbs as a grid of stat cards, so that I can spot which suburbs in the area are lagging.
5. As an operator, I want an "Edit area" action that lets me update name, description, filters (`beds_min`, `beds_max`, `property_types`, `price_min`, `price_max`), so that I can refine an area without dropping to the CLI.
6. As an operator, I want to delete an area, so that I can prune lists I no longer maintain (suburbs remain — the m2m is cleared but the `suburb` row stays).
7. As an operator, I want to add a suburb to an area via a live autocomplete picker that calls a new `/suburbs/autocomplete?q=` endpoint, so that I never have to hit "submit" before I see whether OTH knows about my suburb.
8. As an operator, I want the autocomplete to show the postcode and state alongside each candidate, so that I can disambiguate Mount Coolum (QLD 4573) from any namesake.
9. As an operator, I want to remove a suburb from an area, so that I can let go of areas I no longer track without losing scraped history.
10. As an operator, I want a "Run now" button on the area page that triggers `POST /scrape-lists/{id}/run`, so that I can refresh data without using the CLI.
11. As an operator, I want a confirmation modal before Run-now that states "About to enqueue N suburbs × 3 categories = 3N jobs against onthehouse.com.au", so that I don't trigger expensive traffic by accident.
12. As an operator, I want to trigger a run scoped to a single suburb or a single `(suburb, category)` via the same endpoint with a narrow body, so that I can refresh a stale entry without re-scraping the whole area.
13. As an operator, I want each fanout to create a first-class `scrape_run` row (with `triggered_at`, `completed_at`, `status`, `trigger_source`, `filters_snapshot`) and every `scrape_job` to link back via `run_id`, so that "what was triggered when" is recorded explicitly instead of inferred from timestamps.
14. As an operator, I want the run's `status` and `completed_at` updated atomically the moment its last child job goes terminal, so that the dashboard never lies about whether a run is finished.
15. As an operator, I want a "Past runs" section on the area page listing the last 10 runs with their status pill and counts, so that I can scan recent activity without writing SQL.
16. As an operator, I want to click a past run and see a per-job table grouped by `(suburb, category)` with each job's status, attempts, and error class, so that I can see exactly what failed.
17. As an operator, I want a one-click "Retry failed" action on a run, which re-enqueues just its failed/dead-lettered jobs as a NEW run with `trigger_source='retry'` and `retried_from_run_id` set, so that runs stay immutable and the audit trail is preserved.
18. As an operator, I want individual "Retry" buttons on failed rows in the per-run job table, so that I can re-enqueue a single `(suburb, category)` without re-running every failure.
19. As an operator, I want a "Live" pill and 5-second adaptive polling to kick in whenever the page detects an in-flight run, so that I see updates without manually refreshing.
20. As an operator, I want adaptive polling to stop the moment the run becomes terminal, so that I'm not generating background traffic while idle.
21. As an operator, I want a manual "Refresh" button on every page regardless of polling state, so that I can force a recompute on demand.
22. As an operator, I want each area's summary endpoint (`GET /scrape-lists/{id}/summary`) to return everything the area page needs in one round trip — latest run rollup, suburb count, properties observed, active-listing splits — so that the page doesn't N+1 the API.
23. As an operator, I want to click a suburb card and see the suburb detail page with a 3×2 grid showing how many new and changed snapshots came back per category on the last completed scrape, so that I can tell whether the scrape was productive.
24. As an operator, I want "new" defined as snapshots with `__initial__` in `changed_fields` whose `observed_at` falls within the last completed run's window, so that re-observations of existing listings are not counted as new.
25. As an operator, I want "changed" defined as snapshots without `__initial__` in the same window, so that I can see signal of price/blurb/status movement separately from new listings.
26. As an operator, I want an "in-flight" banner on the suburb page if a run including this suburb is currently running, so that I know my numbers will tick up.
27. As an operator, I want a median sold-price stat (last 30 days, derived from the first snapshot per `recentlysold` listing where `sale_date` falls within the window), so that I can see suburb pricing without leaving the dashboard.
28. As an operator, I want the reconciler to extract `sale_date` from OTH's `raw_payload` into a new nullable `listing.sale_date` column when the category is `recentlysold`, so that the median has a real time anchor instead of approximation via `first_seen_at`.
29. As an operator, I want a median asking price (active for-sale, latest snapshot) and median weekly rent (active for-rent, latest snapshot) alongside the sold median, so that I have a three-pane price profile of the suburb.
30. As an operator, I want a paginated property table on the suburb page (50 per page) with columns address, latest category, latest price, latest observed-at, status pill, so that I can browse the underlying records.
31. As an operator, I want to sort the property table by price and by latest observed-at, so that I can find recent or expensive movement.
32. As an operator, I want a free-text address search box on the property table that does a backend `formatted_address ILIKE %q%` query, so that I can find specific properties without paging.
33. As an operator, I want a row in the property table to link to `/properties/:id`, so that I can drill into a property's history.
34. As an operator, I want the property page to list every listing campaign attached to this address with first/last seen, status, latest price, so that re-listings of the same address are visible.
35. As an operator, I want a listing detail page with a price-history chart drawn from `GET /listings/{id}/snapshots`, so that I can see how a listing's price moved over its lifecycle.
36. As an operator, I want the snapshot table beneath the chart with a column for `changed_fields`, so that I can tell exactly what triggered each snapshot write.
37. As an operator, I want a "raw payload" viewer (collapsed by default) on the listing detail page, so that I can debug OTH parsing issues without dropping to SQL.
38. As an operator, I want the area dashboard, area detail, and suburb detail to support deep linking (URL captures area or suburb id), so that I can bookmark or share specific views.
39. As an operator, I want the UI to live at `/admin/` served by the FastAPI service via `StaticFiles(html=True)`, so that prod is one process and no CORS configuration is needed.
40. As a developer, I want `vite dev` on `:5173` with a `/api → http://localhost:8000` proxy, so that the same `fetch('/api/...')` paths work identically in dev and prod.
41. As a developer, I want the React app to live at `apps/oth-admin/` and not inside the existing `apps/frontend/` (the school-map app), so that admin and consumer concerns are not cross-pollinated.
42. As an operator, I want the service to keep binding to 127.0.0.1 with no auth, so that the local-only PRD posture is unchanged.
43. As an operator, I want a confirm modal on Retry-failed actions stating how many jobs are being re-enqueued, so that I don't accidentally re-scrape an entire run when I meant to fix one job.
44. As a developer, I want narrowed runs implemented by extending the existing `POST /scrape-lists/{id}/run` body with optional `suburb_ids` and `categories` filters, so that callers can target a single `(suburb, category)` through the same well-tested fanout path.
45. As a developer, I want each retry run linked to its parent via `scrape_run.retried_from_run_id`, so that the audit trail of "what was a retry of what" is intact.
46. As a developer, I want the existing `services/property-scraper/` legacy code removed (in a separate cleanup PR — not part of this feature), so that there is one scraper, not two.
47. As a developer, I want the dev DB reset as part of this work rather than backfilled, so that the migration ships clean and no synthesised `scrape_run` rows have to be invented from historical job timestamps.

## Implementation Decisions

### Domain additions

- **New `scrape_run` table**: `id, scrape_list_id NULLABLE, triggered_at, completed_at NULLABLE, status enum(running|succeeded|partial|failed), trigger_source enum(api|cli|scheduler|retry), filters_snapshot JSONB, retried_from_run_id NULLABLE FK→scrape_run.id, created_at`. `scrape_list_id` is nullable so ad-hoc runs (matching the existing nullable scope on `scrape_job`) remain possible.
- **`scrape_job` gains `run_id` bigint FK→`scrape_run.id` NOT NULL**. The producer's transaction now inserts one `scrape_run` row and N `scrape_job` rows in the same commit. Dev data is dropped — no backfill required.
- **`listing` gains `sale_date` DATE NULLABLE**. Populated by the reconciler from `raw_payload` when category is `recentlysold`. Always NULL for `forsale` and `forrent`. The exact `raw_payload` key is to be confirmed against the existing fixture corpus during implementation.

### Deep modules

- **`ScrapeRunFinalizer`**. Single method: `recompute(run_id)` runs one idempotent SQL `UPDATE scrape_run` that derives `(status, completed_at)` from the current state of its child `scrape_job` rows. Invoked from `JobQueue` at the end of every terminal transition (`complete`, `fail`, `deadletter`) and on `reclaim_stuck`. Idempotent under concurrent workers because Postgres serializes the row update. Self-healing: if a worker crashes between writing the job and updating the run, the next worker's terminal transition completes the run.
- **Status derivation logic** (encoded as SQL inside `ScrapeRunFinalizer`):

  ```
  let all_done       = every child job is terminal
  let all_succeeded  = every child job has status='succeeded'
  let any_failed     = at least one child job is failed/deadletter
  let any_succeeded  = at least one child job is succeeded

  status =
    not all_done                                   → 'running'
    all_succeeded                                  → 'succeeded'
    all_done and any_failed and any_succeeded      → 'partial'
    all_done and any_failed and not any_succeeded  → 'failed'

  completed_at = MAX(scrape_job.completed_at) when all_done else NULL
  ```

  (Snippet captures the decision shape — not the exact SQL.)

- **`ScrapeListSummaryService`**. `summary(list_id) → ScrapeListSummary` returning `{id, name, filters, suburb_count, properties_observed, active_listings: {forsale, forrent, recentlysold}, latest_run: {id, triggered_at, completed_at, status, trigger_source, counts: {queued, running, succeeded, failed, deadletter}}, in_flight}`. Pure read coordination; no writes. Implemented as a small number of correlated queries inside one transaction so the numbers are mutually consistent.
- **`SuburbSummaryService`**. `summary(suburb_id) → SuburbSummary` returning `{id, name, postcode, state, last_completed_run: {id, completed_at}, in_flight_run: {id, triggered_at} | null, deltas: {forsale: {new, changed}, forrent: {new, changed}, recentlysold: {new, changed}}, totals: {forsale, forrent, recentlysold}, medians: {sold_30d: {value, n}, asking: {value, n}, rent: {value, n}}}`. The `deltas` window is `[last_completed_run.triggered_at, MAX(scrape_job.completed_at) for this suburb in that run]`.
- **`SaleDateExtractor`**. Pure function over an OTH `raw_payload` dict; returns `date | None`. Lives next to the reconciler. The existing `recentlysold` fixture corpus is the source of truth for the key path.
- **`SuburbAutocomplete`**. Read-only wrapper around OTH's autocomplete endpoint, returning `Match[]`. Does not persist anything (the existing `SuburbResolver` is the only writer). Reused inside the `/suburbs/autocomplete?q=` endpoint.
- **`RunProducer`**. Replaces the implicit producer inside `run_list`. Given `list_id` and optional `{suburb_ids, categories}` narrowing, creates one `scrape_run` row and the corresponding `scrape_job` rows in one transaction. A second method, `retry_failed(run_id)`, reads the failed/dead-letter children of an existing run and creates a new run with `trigger_source='retry'` and `retried_from_run_id` linked. Both the API and CLI call this module.
- **`PropertySearchQuery`**. SQL builder for the suburb-page property table: filters by `suburb_id`, optional `formatted_address ILIKE` search, sorts by latest snapshot price or observed-at, pagination via `limit`/`offset`. Returns each property joined with its latest listing's latest snapshot summary so the table can render without per-row fetches.

### API contracts (new and modified)

- `POST /scrape-lists/{id}/run` — body extended to accept optional `{suburb_ids: int[], categories: ("forsale"|"forrent"|"recentlysold")[]}` narrowing. Response unchanged shape but now also returns `run_id`.
- `POST /scrape-runs/{id}/retry-failed` — re-enqueues failed/dead-letter children as a new run; returns the new `run_id` and child `job_ids`.
- `GET /scrape-runs` — list runs (filter by `list_id`, `status`, `limit`, `offset`).
- `GET /scrape-runs/{id}` — run detail (counts rollup).
- `GET /scrape-runs/{id}/jobs` — per-job table for a run.
- `GET /scrape-lists/{id}/summary` — single-shot area summary DTO as above.
- `GET /suburbs/{id}/summary` — single-shot suburb summary DTO as above.
- `GET /suburbs/autocomplete?q=` — read-only autocomplete; returns `Match[]`. Distinct from `POST /suburbs/resolve` which caches.
- `GET /properties` — extended with `search` query parameter for `formatted_address ILIKE` and additional sort options (`price_desc`, `price_asc`, `observed_at_desc`).
- `GET /properties/{id}` — new endpoint: property + all its listings (with latest-snapshot rollup).
- All write endpoints continue to reject CORS; the SPA is same-origin via `StaticFiles` mount.

### Frontend architecture

- New SPA at `apps/oth-admin/` using React 19 + Vite + Tailwind 4 + Recharts + Lucide. Matches the toolchain of `apps/frontend/` but is a sibling, not a route within it.
- **Pages**: `AreasIndex`, `AreaDetail`, `SuburbDetail`, `PropertyDetail`, `ListingDetail`, `RunDetail`.
- **Shared components**: `StatCard`, `RunStatusPill`, `CategorySplit`, `SuburbAutocomplete` (debounced 250ms, 5 results, postcode + state badges), `RunConfirmModal`, `PriceChart` (Recharts line over snapshot history), `PropertyTable` (paginated, sortable, searchable).
- **Hook**: `useAdaptivePoll(fetcher, { whileRunning: boolean })` — does one fetch on mount; if the result shows an in-flight run, polls every 5 seconds until it isn't. Used by area, suburb, and run pages.
- **API client** at `src/api/`, one typed module per resource (`areas.ts`, `suburbs.ts`, `runs.ts`, `properties.ts`, `listings.ts`). Same `/api/...` paths in dev (via Vite proxy) and prod (same-origin).
- **Styling posture**: admin density (no hero imagery, tight tables, neutral palette), Lucide icons, consistent Tailwind 4 tokens shared in spirit with `apps/frontend/`.

### Bundle serving

- FastAPI mounts the built React bundle at `/admin/` via `StaticFiles(directory=..., html=True)`. Build step in `apps/oth-admin/Taskfile.yml` builds and copies output to `services/oth-scraper/static/admin/`.
- Dev: `vite dev` on `:5173`, proxy `/api → http://localhost:8000`. Hot reload works; calls match prod paths.

### Filter and form decisions

- Area create/edit form mirrors `ScrapeListFilters` exactly: number inputs for `beds_min/max` and `price_min/max`, multi-select for `property_types` (House, Townhouse, Unit, Apartment, Land). No bathroom filter (matches PRD scope). `cron_schedule` field is hidden in v1.
- The 3×2 New/Changed grid on the suburb page renders zeros when the last completed run window has no snapshots in a category — that itself is a signal worth seeing.

## Testing Decisions

A good test in this codebase exercises external behaviour of a module — given input, observe output or persisted side effects — rather than asserting on private structure. Tests are fast, deterministic, and survive refactors that preserve behaviour. Existing test patterns (pytest + pytest-asyncio + a Postgres test container; recorded JSON fixtures for OTH responses) carry over for backend; the frontend has no test infrastructure yet and v1 will not introduce a full suite.

### Modules with explicit unit-test coverage

- **`ScrapeRunFinalizer`** — integration tests against a real Postgres test container. Table-driven over child-job state combinations: all queued → `running`; mixed running/queued → `running`; all succeeded → `succeeded` + `completed_at` set; mixed succeeded + failed → `partial`; all failed → `failed`. Re-invocation idempotent (running it twice leaves the row unchanged). Concurrent invocation safe (two simultaneous calls converge to one final state).
- **`SaleDateExtractor`** — pure unit. Table-driven over the existing `recentlysold` fixture corpus at `services/oth-scraper/tests/fixtures/`. Cases: payload has the field → returns the date; field missing or null → returns None; malformed date string → returns None. Highest leverage per line.
- **`SuburbAutocomplete`** — unit against a mocked OTH client. Asserts that the wrapper passes through OTH's candidate list verbatim and never touches the DB.

### Modules with integration coverage

- **`ScrapeListSummaryService` / `SuburbSummaryService`** — integration tests against a real Postgres test container with seeded `scrape_list`, `scrape_run`, `scrape_job`, `property`, `listing`, `listing_snapshot` rows. Cases: empty list → all-zeros DTO; one completed run → summary picks it up; one in-flight run + a prior completed run → `latest_run` is the in-flight, `last_completed_run` on the suburb DTO is the prior; deltas window strictly bounded by the run timestamps.
- **`RunProducer`** — integration: full-list fanout creates 1 + 3N rows linked by `run_id`; narrowed fanout with `suburb_ids=[X]` creates 1 + 3 rows; `retry_failed` of a run with K failed jobs creates 1 new run + K new jobs with `retried_from_run_id` set; the original run is not mutated.
- **Reconciler `sale_date` extraction** — extends existing reconciler integration tests; assert that a `recentlysold` payload with a sale date populates `listing.sale_date` on first observation and never overwrites it.
- **FastAPI endpoints** — one happy-path test per new endpoint (`/scrape-lists/{id}/summary`, `/suburbs/{id}/summary`, `/suburbs/autocomplete`, `/scrape-runs/...`, narrowed `/run` body, `/properties/{id}`). Plus the `search` parameter case on `/properties`.

### Frontend testing

- v1: smoke-level component tests only. Two are worth writing:
  - `SuburbAutocomplete` — debounce behaviour and candidate rendering (postcode + state badges visible, empty state message).
  - `PriceChart` — given a sample snapshot history, asserts the chart has the right number of points and that price values are extracted correctly.
- Exhaustive page-level tests deferred. Manual smoke-test pass during PR review.

### Prior art

The `services/oth-scraper` test suite already establishes pytest + pytest-asyncio + a Postgres test container + recorded OTH fixtures. The PRD's "good test" definition (external behaviour, not implementation detail) carries forward. The snapshot diff engine's table-driven style is the template for `ScrapeRunFinalizer`.

## Out of Scope

- **Universe / housing-stock figures per suburb** — no data source is wired up; ABS census is external and stale. A nullable `suburb.housing_stock_estimate` column can land later without disruption.
- **Map-based property exploration** — table view only in v1; map view is deferred.
- **Scheduling** — `scrape_list.cron_schedule` column remains reserved; no scheduler runs.
- **Days-on-market, price-drop history, per-property-type splits** beyond the three medians bundle.
- **Authentication, multi-user, LAN binding** — service stays 127.0.0.1, no auth.
- **Migrating legacy data from `services/property-scraper`** — schemas are incompatible and the legacy service is being removed in a separate cleanup PR.
- **Server-Sent Events / WebSockets** for live updates — adaptive polling is sufficient for one user on localhost.
- **Backfilling existing `scrape_job` rows into synthesised runs** — dev DB will be reset.
- **Deleting individual runs** from the UI — runs are immutable audit trail. (If this turns out to be a real need, add a "Delete run (cascade jobs)" admin action in v2.)
- **Frontend test suite beyond smoke** — no Cypress/Playwright/Vitest infra is being introduced in v1.

## Further Notes

- The biggest single behavioural risk in this work is the `ScrapeRunFinalizer` update path: every terminal job transition triggers it, and if it's wrong the dashboard lies in subtle ways. It deserves the most test coverage of any new module, and its SQL should be reviewed by hand before merge.
- Once `scrape_run` is first-class, the v2 scheduler has an obvious place to attach (`trigger_source='scheduler'` plus a periodic task creating new runs against lists whose `cron_schedule` is due).
- The `retried_from_run_id` chain forms a natural lineage graph. A future "Run timeline" view per area can render it; v1 just exposes the field on the run detail page as text.
- The `/admin/` mount is a small change to `api/app.py`; if the `static/admin/` directory is missing in dev (because the SPA hasn't been built), the mount should be conditional so backend dev workflows don't break.
- The dev story (`vite dev` + proxy) means the same code can run against either a local FastAPI on `:8000` or a remote one with no change to the SPA — useful if you ever spin the scraper up on a homelab box and want to drive it from your laptop.
- The legacy `services/property-scraper/` removal is intentionally scoped to a separate PR — keeping this feature's diff focused on the new admin surface.
