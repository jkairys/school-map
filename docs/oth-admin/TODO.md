# OTH admin — implementation issues

Tracer-bullet vertical slices for the [OTH admin PRD](./PRD.md). Each issue is sized to be implementable in a single Claude session: bounded schema/API/tests, plus a small UI piece where relevant. Issues are grouped by dependency layer — pick any unblocked one to start.

## Overview

| # | Title | Type | Blocked by | PRD user stories |
|---|---|---|---|---|
| 01 | First-class `scrape_run` entity + runs API | AFK | — | 13, 14, 15, 16 |
| 02 | Extract `listing.sale_date` from `raw_payload` | AFK | — | 27, 28 |
| 03 | Area summary endpoint | AFK | 01 | 1, 2, 22 |
| 04 | Suburb summary endpoint + medians | AFK | 01, 02 | 23, 24, 25, 26, 27, 29 |
| 05 | Narrowed runs + retry-failed | AFK | 01 | 12, 17, 44, 45 |
| 06 | Suburb autocomplete + property search/detail endpoints | AFK | — | 7, 8, 30, 31, 32, 33, 34 |
| 07 | SPA scaffold + Areas dashboard | AFK | 03 | 1, 2, 3, 39, 40, 41, 42 |
| 08 | Area detail + Run-now + adaptive polling | AFK | 05, 07 | 4, 5, 6, 10, 11, 15, 19, 20, 21 |
| 09 | Add-suburb autocomplete picker | AFK | 06, 08 | 7, 8, 9 |
| 10 | Suburb detail page + property table | AFK | 04, 06, 08 | 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 38 |
| 11 | Property + Listing detail pages | AFK | 10 | 33, 34, 35, 36, 37 |
| 12 | Run detail page + retry buttons | AFK | 05, 08 | 16, 17, 18, 43 |

All slices are AFK. Slice 02 has one open question (the exact `raw_payload` key) that the implementer resolves from the existing fixture corpus, not from the user.

---

## 01 — First-class `scrape_run` entity + runs API

### Parent
[PRD](./PRD.md)

### What to build

Replace the implicit "fanout = jobs sharing a `created_at`" inference with a first-class `scrape_run` row. The producer transaction now inserts one `scrape_run` and N `scrape_job` rows together; every job links back via `run_id`. A new `ScrapeRunFinalizer` recomputes `(status, completed_at)` on the parent run at every terminal job transition. Three read endpoints expose the run history. Dev DB is reset — no backfill.

Status derivation (encoded as one idempotent SQL statement, drawn from grilling):

```
all_done       = every child job is terminal (succeeded/failed/deadletter)
all_succeeded  = every child job is succeeded
any_failed     = at least one child failed/deadletter
any_succeeded  = at least one child succeeded

status =
  not all_done                                  → 'running'
  all_succeeded                                 → 'succeeded'
  all_done, any_failed, any_succeeded           → 'partial'
  all_done, any_failed, not any_succeeded       → 'failed'

completed_at = MAX(scrape_job.completed_at) when all_done else NULL
```

`scrape_run` schema: `id, scrape_list_id NULLABLE, triggered_at, completed_at NULLABLE, status enum(running|succeeded|partial|failed), trigger_source enum(api|cli|scheduler|retry), filters_snapshot JSONB, retried_from_run_id NULLABLE FK→scrape_run.id, created_at`. `scrape_job` gains `run_id` bigint FK→`scrape_run.id` NOT NULL.

### Acceptance criteria

- [ ] Alembic migration adds `scrape_run` table and `scrape_job.run_id NOT NULL` (dev data dropped)
- [ ] `POST /scrape-lists/{id}/run` creates a `scrape_run` row in the same transaction as job fanout
- [ ] `oth list run` CLI does the same (shared service layer)
- [ ] `JobQueue.complete/fail/deadletter/reclaim_stuck` invoke `ScrapeRunFinalizer.recompute(run_id)` after their state write
- [ ] Finalizer SQL is idempotent (re-invocation leaves the row unchanged) and concurrency-safe (two simultaneous calls converge to the same state)
- [ ] Reclaim of a stuck job from a previously-terminal run flips it back to `running`
- [ ] `GET /scrape-runs?list_id=&status=&limit=&offset=` lists runs
- [ ] `GET /scrape-runs/{id}` returns run detail with per-status counts rollup
- [ ] `GET /scrape-runs/{id}/jobs` returns the run's child jobs
- [ ] Finalizer has table-driven integration tests over the state-combination matrix
- [ ] Producer integration test asserts 1 + 3N rows on a 1-suburb list run, all linked via `run_id`

### Blocked by
None — can start immediately.

---

## 02 — Extract `listing.sale_date` from `raw_payload`

### Parent
[PRD](./PRD.md)

### What to build

A pure `SaleDateExtractor` that reads OTH `raw_payload` and returns a `date | None`. Reconciler calls it for `recentlysold` listings on first observation; result is persisted on a new nullable `listing.sale_date DATE` column. Always NULL for `forsale` / `forrent`. Never overwrites once set.

The exact key in `raw_payload` is to be determined from `services/oth-scraper/tests/fixtures/` — inspect the `recentlysold` corpus and pick the field that consistently carries the actual sale date.

### Acceptance criteria

- [ ] Alembic migration adds `listing.sale_date DATE NULLABLE`
- [ ] `SaleDateExtractor` is a pure function (no DB, no I/O) returning `date | None`
- [ ] Extractor has unit tests over the `recentlysold` fixture corpus covering: field present → date; field missing → None; malformed date → None
- [ ] Reconciler populates `sale_date` on first snapshot of a `recentlysold` listing
- [ ] Re-observing the same listing does not overwrite `sale_date`
- [ ] Reconciler integration test asserts the populated column

### Blocked by
None — can start immediately.

---

## 03 — Area summary endpoint

### Parent
[PRD](./PRD.md)

### What to build

A single read endpoint that returns everything the Areas dashboard and Area detail page need for one area in one round trip. Implemented as a `ScrapeListSummaryService.summary(list_id)` that runs a small set of correlated queries in one transaction so the numbers are mutually consistent.

Response shape:

```
{
  id, name, description, filters, suburb_count,
  properties_observed: int,             # distinct property.id by suburb membership
  active_listings: { forsale, forrent, recentlysold },   # closed_at IS NULL
  latest_run: {
    id, triggered_at, completed_at, status, trigger_source,
    counts: { queued, running, succeeded, failed, deadletter }
  } | null,
  in_flight: bool                       # latest_run.status === 'running'
}
```

### Acceptance criteria

- [ ] `ScrapeListSummaryService.summary(list_id)` returns the DTO above
- [ ] `GET /scrape-lists/{id}/summary` exposes the DTO
- [ ] 404 when list doesn't exist
- [ ] All counts are computed within a single transaction (no read-skew between fields)
- [ ] Integration tests cover: empty list, list with one completed run, list with one in-flight run, list with no runs

### Blocked by
- 01 (needs `scrape_run` to derive `latest_run`)

---

## 04 — Suburb summary endpoint + medians

### Parent
[PRD](./PRD.md)

### What to build

`SuburbSummaryService.summary(suburb_id)` returning everything the Suburb detail page needs. Anchors deltas to the last completed run that included this suburb; medians come from `listing_snapshot.price`.

Response shape:

```
{
  id, name, postcode, state,
  last_completed_run: { id, completed_at } | null,
  in_flight_run: { id, triggered_at } | null,
  deltas: {                              # window = [last_completed_run.triggered_at, MAX(scrape_job.completed_at for this suburb in that run)]
    forsale:       { new, changed },
    forrent:       { new, changed },
    recentlysold:  { new, changed }
  },
  totals: { forsale, forrent, recentlysold },   # all listings ever, by category
  medians: {
    sold_30d: { value, n },              # first snapshot per recentlysold listing where sale_date >= today - 30d
    asking:   { value, n },              # active forsale, latest snapshot price
    rent:     { value, n }               # active forrent, latest snapshot price
  }
}
```

"new" = snapshots with `__initial__` in `changed_fields` within the window. "changed" = snapshots in the window without `__initial__`.

### Acceptance criteria

- [ ] `GET /suburbs/{id}/summary` returns the DTO
- [ ] 404 when suburb doesn't exist
- [ ] Median sold-30d uses `listing.sale_date` (from 02), not `first_seen_at`
- [ ] Median takes the FIRST snapshot per recentlysold listing (canonical sale price)
- [ ] Asking/rent medians use latest snapshot of active listings only
- [ ] Deltas window correctly bounded; zero counts returned when no snapshots fell in window
- [ ] `in_flight_run` populated if any job for this suburb is currently queued/running
- [ ] Integration tests with seeded fixtures cover: no runs, completed run with mixed new/changed, in-flight run, empty windows, NULL prices

### Blocked by
- 01 (scrape_run windowing)
- 02 (sale_date for median)

---

## 05 — Narrowed runs + retry-failed

### Parent
[PRD](./PRD.md)

### What to build

Extend `POST /scrape-lists/{id}/run` body with optional `suburb_ids: int[]` and `categories: ("forsale"|"forrent"|"recentlysold")[]` to narrow the fanout. Add `POST /scrape-runs/{id}/retry-failed` which re-enqueues the failed/dead-letter children of an existing run as a NEW run with `trigger_source='retry'` and `retried_from_run_id` linked. Both call a `RunProducer` module shared between API and CLI.

The original run is never mutated; status stays at whatever it was. Retry creates a fresh `scrape_run` row whose jobs are a subset of the parent's `(suburb, category)` pairs (only the failed ones).

### Acceptance criteria

- [ ] `RunProducer.create_run(list_id, suburb_ids=None, categories=None, trigger_source='api')` creates one `scrape_run` + the appropriate jobs in one transaction
- [ ] `RunProducer.retry_failed(run_id)` reads the failed/deadletter children, creates a new run, sets `retried_from_run_id`
- [ ] `POST /scrape-lists/{id}/run` accepts the optional narrowing body (omitted body = full fanout)
- [ ] `POST /scrape-runs/{id}/retry-failed` returns the new run_id + child job_ids
- [ ] CLI mirror: `oth list run --suburb=X --category=forsale` and `oth run retry-failed <run_id>`
- [ ] Narrowing rejects unknown suburb_ids or categories with 422
- [ ] Retry of a run with no failed jobs returns 422 (or 200 with empty job list — pick and document)
- [ ] Integration tests: full fanout, single-suburb narrow, single-category narrow, retry of partial run, retry of all-succeeded run, retry chain (retry of a retry → parent chain is intact)

### Blocked by
- 01 (scrape_run + run_id + trigger_source + retried_from_run_id)

---

## 06 — Suburb autocomplete + property search/detail endpoints

### Parent
[PRD](./PRD.md)

### What to build

Three read additions to support the SPA's pickers and tables:

1. `GET /suburbs/autocomplete?q=` — returns OTH autocomplete candidates verbatim. Read-only; does NOT cache (the existing `POST /suburbs/resolve` is the only writer).
2. `GET /properties` — extend with optional `search` query parameter (`formatted_address ILIKE %q%`) and sort options (`price_desc`, `price_asc`, `observed_at_desc`). Returns each row joined with its latest listing's latest snapshot summary (price, observed_at, status) so the table renders without per-row fetches.
3. `GET /properties/{id}` — new endpoint returning the property plus every listing campaign attached, each with its latest-snapshot summary.

### Acceptance criteria

- [ ] `SuburbAutocomplete` module wraps OTH autocomplete; never touches the DB
- [ ] `GET /suburbs/autocomplete?q=` returns `Match[]`; empty list when nothing matches
- [ ] `GET /properties?suburb=&search=&sort=&limit=&offset=` honours all three filters; response includes latest-snapshot rollup per row
- [ ] `GET /properties/{id}` returns property + listings + each listing's latest snapshot summary
- [ ] 404 on unknown property
- [ ] Tests: autocomplete passthrough; property search by partial address; sort orderings; property detail with multiple listing campaigns

### Blocked by
None — can start immediately.

---

## 07 — SPA scaffold + Areas dashboard

### Parent
[PRD](./PRD.md)

### What to build

Bootstrap `apps/oth-admin/` (React 19 + Vite + Tailwind 4 + Lucide). FastAPI mounts the built bundle at `/admin/` via `StaticFiles(html=True)` (mount is conditional on the static dir existing so backend dev doesn't break). Vite dev proxy points `/api → http://localhost:8000`. Build typed API client modules per resource. Implement the Areas dashboard consuming `GET /scrape-lists` + per-row `GET /scrape-lists/{id}/summary` (a small N+1 here is fine for dozens of areas; can refactor to a list-summary endpoint later if it bites).

Shared components needed for this and later slices: `StatCard`, `RunStatusPill`, `CategorySplit`.

### Acceptance criteria

- [ ] `apps/oth-admin/` scaffolded with Vite + React 19 + Tailwind 4 + Lucide
- [ ] `Taskfile.yml` with `dev`, `build`, `lint` targets; `build` outputs into `services/oth-scraper/static/admin/`
- [ ] Vite dev proxy routes `/api` to FastAPI
- [ ] FastAPI mounts `/admin/` via `StaticFiles(html=True)` conditional on directory existing
- [ ] Same-origin in prod; `fetch('/api/...')` works identically in dev and prod
- [ ] `/areas` route lists every area as a card showing name, suburb count, properties observed, active-listing split, latest run status pill, last-triggered timestamp
- [ ] Each area card links to `/areas/:id` (target page may not exist yet — link is fine)
- [ ] Manual smoke: open `/admin/` against a seeded DB, see real numbers

### Blocked by
- 03 (Areas dashboard depends on `/scrape-lists/{id}/summary`)

---

## 08 — Area detail + Run-now + adaptive polling

### Parent
[PRD](./PRD.md)

### What to build

`/areas/:id` page: shows area metadata, filters (read-only here; edit form drops to a modal), the area's suburbs as a stat-card grid, and an expandable "Past runs" section listing the last 10 runs (status pill, counts, duration). Each past run links to `/runs/:id` (target page lands in slice 12; placeholder route OK).

Run-now button triggers `POST /scrape-lists/{id}/run` after a confirm modal stating "N suburbs × 3 categories = 3N jobs". The `useAdaptivePoll` hook detects an in-flight run and polls `GET /scrape-runs/{id}` every 5s until terminal, then stops. A "Live" pill is visible while polling. Manual "Refresh" button always present.

Area edit and delete actions land here (form mirrors `ScrapeListFilters` Pydantic shape: number inputs for beds/price min-max, multi-select for property types; `cron_schedule` hidden).

### Acceptance criteria

- [ ] `/areas/:id` renders area metadata, filters, suburb grid, past-runs section
- [ ] Run-now button posts to the existing endpoint after a confirm modal; modal shows the job count and a Cancel
- [ ] `useAdaptivePoll(fetcher, { whileRunning })` hook: one fetch on mount, polls every 5s while the predicate is true, stops when false
- [ ] "Live" pill visible only while polling
- [ ] Manual "Refresh" button forces a re-fetch regardless of polling state
- [ ] Area edit form persists via `PUT /scrape-lists/{id}`
- [ ] Area delete posts to `DELETE /scrape-lists/{id}` after confirm
- [ ] Manual smoke: trigger a run, see the status pill tick from `running` → `succeeded/partial/failed` without a page reload

### Blocked by
- 05 (Run-now uses the producer; narrowed body is exercised here for default = full fanout)
- 07 (needs SPA scaffold)

---

## 09 — Add-suburb autocomplete picker

### Parent
[PRD](./PRD.md)

### What to build

`SuburbAutocomplete` component: a debounced (250ms) text input that calls `GET /suburbs/autocomplete?q=` and renders up to 5 candidates, each as `Name  ·  Postcode State`. Selection captures the fully-qualified `{name, postcode, state}` for the subsequent `POST /scrape-lists/{id}/suburbs`. Empty state: "no matches — try a different spelling". Wired into the area detail page as an "Add suburb" affordance. Remove-suburb action also lives here.

### Acceptance criteria

- [ ] Component debounces input by 250ms before fetching
- [ ] Renders max 5 results, each with postcode + state badges
- [ ] Empty state visible when query is non-empty but returns nothing
- [ ] Selecting a candidate populates a fully-qualified payload
- [ ] Add-suburb submit posts to `POST /scrape-lists/{id}/suburbs` with the picked candidate
- [ ] Remove-suburb posts to `DELETE /scrape-lists/{id}/suburbs/{suburb_id}` after a confirm
- [ ] On 409 ambiguity (edge case if the picker somehow gives an ambiguous payload), show the candidates inline
- [ ] Smoke test asserts debounce + candidate rendering

### Blocked by
- 06 (autocomplete endpoint)
- 08 (area detail page is where this lives)

---

## 10 — Suburb detail page + property table

### Parent
[PRD](./PRD.md)

### What to build

`/suburbs/:id` page consuming `GET /suburbs/{id}/summary`. Lays out:

- Suburb metadata (name, postcode, state)
- In-flight run banner when `in_flight_run` is non-null
- Last completed run timestamp + linked run id
- 3×2 New/Changed grid (rows = New / Changed, columns = forsale / forrent / sold)
- Three median tiles (sold-30d, asking, rent) showing value + n
- Total listings per category
- `PropertyTable`: server-paginated (50/page), columns address / latest category / latest price / latest observed-at / status pill; sortable by price + observed-at; free-text address search box (debounced 250ms) hitting `GET /properties?suburb=&search=&sort=&limit=&offset=`; each row links to `/properties/:id`

### Acceptance criteria

- [ ] `/suburbs/:id` renders the summary DTO faithfully
- [ ] 3×2 grid renders zeros for empty categories without breaking
- [ ] Medians display as currency / "no data" when n=0
- [ ] In-flight banner appears only when `in_flight_run` is set
- [ ] `PropertyTable` paginates, sorts, and searches via backend params; URL captures page/sort/search so deep links work
- [ ] Adaptive polling on this page when `in_flight_run` is present
- [ ] Manual smoke against seeded data: drill from area → suburb, all numbers match SQL

### Blocked by
- 04 (suburb summary endpoint)
- 06 (property search endpoint)
- 08 (SPA navigation + polling hook)

---

## 11 — Property + Listing detail pages

### Parent
[PRD](./PRD.md)

### What to build

`/properties/:id` page: property address, suburb, every listing campaign ever attached (category, first_seen, last_seen, closed_at, latest price), each linking to `/listings/:id`. Re-listing count is just `listings.length`.

`/listings/:id` page: header (category, status, agent/agency, dates), price-history chart (Recharts line over `GET /listings/{id}/snapshots`, x = `observed_at`, y = `price`, dots annotated with `changed_fields`), snapshot table beneath with all columns including `changed_fields`, and a collapsed "raw payload" viewer for the latest snapshot.

### Acceptance criteria

- [ ] `/properties/:id` lists all listings with the rollup from `GET /properties/{id}`
- [ ] `/listings/:id` price chart renders correctly when there is ≥ 1 snapshot
- [ ] Single-snapshot listing renders a single point without crashing the chart
- [ ] Snapshots with NULL price are skipped in the chart but shown in the table
- [ ] Snapshot table shows `changed_fields` as a comma-separated chip list
- [ ] Raw payload viewer toggles open and pretty-prints JSON
- [ ] Smoke test: `PriceChart` given a fixture of 5 snapshots renders 5 points

### Blocked by
- 10 (links from suburb's property table)

---

## 12 — Run detail page + retry buttons

### Parent
[PRD](./PRD.md)

### What to build

`/runs/:id` page consuming `GET /scrape-runs/{id}` + `GET /scrape-runs/{id}/jobs`. Header shows the run's status pill, trigger source, triggered/completed timestamps, and (if applicable) a "Retried from #X" backlink. Job table groups rows by `(suburb, category)` with status, attempts, last error class, last error message.

Two retry affordances:
- Per-row "Retry" on each failed/deadletter row → calls the narrowed-run endpoint (`POST /scrape-lists/{list_id}/run` with `suburb_ids=[X], categories=[Y]`) after a confirm modal naming the single job
- Header "Retry all failed" → calls `POST /scrape-runs/{id}/retry-failed` after a confirm modal naming the failed-job count

Both navigate to the new run on success.

Adaptive polling on this page if the run is `running`.

### Acceptance criteria

- [ ] `/runs/:id` renders status header + job table grouped by `(suburb, category)`
- [ ] "Retried from #X" backlink appears when `retried_from_run_id` is set
- [ ] Per-row retry visible only on failed/deadletter rows
- [ ] Header "Retry all failed" visible only when at least one failed job exists
- [ ] Both retry paths confirm before firing
- [ ] Both retry paths navigate to the freshly-created run's page on success
- [ ] Adaptive polling kicks in when the run is `running`
- [ ] Manual smoke: simulate a failure (kill worker mid-job or seed a deadletter), open the run page, click retry, see a new run row with `retried_from_run_id` set

### Blocked by
- 05 (retry and narrowed-run endpoints)
- 08 (SPA scaffold + polling hook)
