# PRD — OTH Scraper Service

> **Live domain model reference**: `docs/scraper-service/DOMAIN_MODEL.md` — what's actually in the database now (grounded in the SQLAlchemy models, not just this PRD's design intent). Reference that for current schema; reference this PRD for original design rationale.

## Problem Statement

I want to track Australian residential real estate listings — for sale, for rent, and recently sold — across a curated set of suburbs that I care about, and watch how those listings change over time (price drops, blurb edits, status transitions). Today I have a one-shot Python scraper that targets `onthehouse.com.au` for Brisbane sold properties only: it dumps per-suburb JSON files, has no notion of the same listing across runs, can't track price history, and is hardcoded to "3–4BR Houses, last 90 days, sold". I can't manage suburbs as named lists, I can't kick off a coordinated multi-suburb scrape, and there's no durable schema I can run analytics against. Anti-bot defences on OTH already require a Playwright fallback in the existing tool, which is fragile.

## Solution

A standalone microservice that owns the full lifecycle of property-listing data:

- I define **scrape lists** — named collections of Australian suburbs, each carrying its own filter set (bedroom range, property types, price range).
- I trigger a scrape of a list via REST or CLI; the service **fans out** one job per `(suburb × category)` for `ForSale`, `ForRent`, `RecentlySold`, queued in Postgres.
- A configurable pool of **workers** consumes the queue. Each worker bootstraps a stealth browser session (camoufox) once, captures the cookies/anti-bot tokens, and reuses them for fast HTTP calls against OTH's search API. Sessions rotate on age, request count, or block.
- Results land in a normalised `Property → Listing → ListingSnapshot` schema in Postgres (with PostGIS for lat/lon). Snapshots are only written when a relevant field changes; raw OTH JSON is preserved on every snapshot for re-parsing later.
- A small read API exposes lists, jobs, properties, listings, and snapshot history so I can build analytics on top.

The service runs locally via `docker-compose` (api, worker, postgres). I drive it interactively for v1; later versions add detail-page enrichment, two-pass closure resolution, scheduling, and a map UI.

## User Stories

1. As an analyst, I want to add a suburb to the system by name (e.g. "Little Mountain"), so that the service resolves it to the correct postcode/state via OTH's autocomplete and caches it.
2. As an analyst, I want disambiguation when a suburb name matches multiple postcodes, so that I can pick the right one rather than silently scraping the wrong area.
3. As an analyst, I want to create a named scrape list (e.g. "Sunshine Coast family homes"), so that I can group suburbs I care about under one trigger.
4. As an analyst, I want each scrape list to carry its own filters — bedroom min/max, property types, price min/max — so that different lists encode different research questions.
5. As an analyst, I want to add and remove suburbs from a scrape list without losing prior scrape history, so that I can evolve the list over time.
6. As an analyst, I want to trigger a scrape of a list via a single REST call or CLI command, so that one action covers all suburbs and categories on the list.
7. As an analyst, I want each `(suburb × category)` to become an independently-queued job, so that one bad suburb or category doesn't fail the whole batch and parallelism is maximal.
8. As an analyst, I want workers to claim jobs from a Postgres-backed queue using `SKIP LOCKED`, so that adding worker capacity is just `docker compose up --scale worker=N`.
9. As an analyst, I want a configurable concurrency setting and a per-host token-bucket rate limiter, so that I can balance throughput against anti-bot exposure.
10. As an analyst, I want each worker to bootstrap a stealth browser (camoufox) once and reuse the captured cookies for httpx calls, so that scraping is fast but resilient to OTH's anti-bot.
11. As an analyst, I want sessions to rotate after N requests, after a max age, or on a 403/429, so that long-running workers don't get stale or fingerprinted.
12. As an analyst, I want transient HTTP errors to retry up to 3× with exponential backoff, anti-bot blocks to drop-and-rebootstrap-and-retry-once, and parse errors to dead-letter without retry, so that the right failure class gets the right response.
13. As an analyst, I want failed jobs preserved in a dead-letter table with the original error and raw payload, so that I can inspect and replay them.
14. As an analyst, I want every Property identified by OTH's `propertyId` (with `(address, postcode)` as a fallback unique key), so that re-listings of the same physical address are linked.
15. As an analyst, I want lat/lon stored as a `geography(Point, 4326)` column, so that future spatial queries (e.g. "listings within school catchment X") are first-class.
16. As an analyst, I want each marketing campaign (a `Listing`) to have its own row with `category`, `first_seen_at`, `last_seen_at`, `closed_at`, `closure_reason`, so that I can ask "how many times has this property been listed".
17. As an analyst, I want a new `ListingSnapshot` to be written only when a relevant field changes (price, blurb, particulars, status), so that the snapshot table tracks signal not heartbeats.
18. As an analyst, I want every snapshot to retain the full OTH JSON in a `raw_payload` JSONB column, so that I can reparse old data when I add fields later.
19. As an analyst, I want every observation (changed or not) to bump `last_seen_at` on the Listing, so that I can detect listings that disappear from the feed.
20. As an analyst, I want a Listing not seen in N consecutive scrapes of its `(suburb, category)` to auto-close with `reason='unknown'`, so that v1 has a working soft-expiry without needing detail-page hits.
21. As an analyst, I want the read API to expose minimal CRUD and targeted views — list scrape lists, list jobs, list properties by suburb, list active listings by `(suburb, category)`, list snapshots for a listing — so that I can spot-check via Swagger and a future UI has endpoints to call.
22. As an analyst, I want the service to bind to `127.0.0.1` only and run with no auth, so that I don't pay an auth tax on a local-only personal tool.
23. As an analyst, I want the API and CLI to share a single service layer, so that running `oth list run` and `POST /scrape-lists/{id}/run` are guaranteed equivalent.
24. As an analyst, I want the service to ship as `docker-compose` with `api`, `worker`, `postgres`, so that `docker compose up` is the only command I need.
25. As an analyst, I want the existing `services/property-scraper` left in place as read-only reference until the new service is at parity, so that I don't lose a working tool mid-build.
26. As a future-me, I want a `cron_schedule` column reserved on `ScrapeList` even though v1 is manual-trigger only, so that v2 can plug in a scheduler without a migration.
27. As a future-me, I want detail-page enrichment (blurb, land size, photos) and two-pass closure resolution architected as opt-in flags from day one, so that v2 can promote them without restructuring the worker.
28. As a developer, I want a recorded-fixtures test suite for OTH responses and a single opt-in live E2E gated by an env flag, so that CI is fast and quiet but I can still smoke-test against real OTH before releases.

## Implementation Decisions

### Stack

- Python 3.11+, FastAPI, asyncio, Typer CLI, SQLAlchemy 2.0 async + Alembic, httpx, camoufox.
- Postgres 16 with PostGIS extension. Run via `docker-compose` alongside the service.
- `docker-compose.yml` defines three services: `api`, `worker`, `postgres`. The `api` and `worker` images are identical; only the entrypoint differs. Worker count scaleable via `docker compose up --scale worker=N`.
- Service binds to `127.0.0.1` only; no authentication.

### Module breakdown

Deep modules (testable in isolation, narrow interfaces):

- **Suburb resolver** — wraps OTH's location-autocomplete endpoint; `resolve(name) → ResolvedSuburb | list[Match]`. Caches results in the `suburb` table.
- **OTH API client** — Pydantic models for OTH's search request/response shapes. Maps `(suburb, category, filters, page) → JSON payload`; parses response JSON → typed `OTHListing` objects. Knows nothing about the DB.
- **Scrape session** — owns the camoufox lifecycle. `bootstrap()` launches camoufox, navigates OTH, captures cookies + headers; subsequent calls go via httpx using those headers. Rotates on `requests >= N`, `age >= T`, or on a 403/429. Async context manager.
- **Snapshot diff engine** — pure: `diff(prev: ListingSnapshot | None, new: OTHListing) → ChangedFields | None`. The fields whose change triggers a new snapshot are an explicit allow-list (`price`, `blurb`, `bedrooms`, `bathrooms`, `parking`, `land_size_sqm`, `property_type`, `status`).
- **Job queue** — Postgres-backed wrapper exposing `enqueue(job)`, `claim_next() -> Job | None` (`SELECT ... FOR UPDATE SKIP LOCKED`), `complete(job)`, `fail(job, error_class)`. Backs the `scrape_jobs` table.
- **Rate limiter** — token-bucket per host (`onthehouse.com.au`), default 1 req / 1.5–3.0s with jitter; shared across in-process worker tasks. Async-aware.

Coordination modules:

- **Listing reconciler** — for one batch of API results: upsert `Property`, open or update the matching `Listing`, run the diff engine, write a `ListingSnapshot` on change, bump `last_seen_at` on every observation. Runs the soft-expiry sweep after enumeration: any `Listing` where `(suburb_id, category)` matches the job and `last_seen_at` is older than the soft-expiry threshold gets `closed_at=now()`, `closure_reason='unknown'`.
- **ScrapeList service** — CRUD for lists, validates filter JSON shape, manages the list↔suburb m2m, exposes `run(list_id)` which fans out `(suburb × category)` jobs into the queue.
- **Worker loop** — claim → load job filters → ensure session → call OTH API client paginated until empty → reconcile each page → mark complete. Tiered error handling: transient (5xx/timeout) retries up to 3× with exp backoff; anti-bot (403/429/Cloudflare wall) tears down the camoufox session, rebootstraps, retries once; parse errors dead-letter immediately.
- **FastAPI app + Typer CLI** — both call the same service-layer functions. CLI commands mirror REST endpoints.

### Schema

- `suburb` — id, name, postcode, state, oth_slug, resolved_at. Unique on `(name, postcode, state)`.
- `scrape_list` — id, name, description, filters (JSONB: `{beds_min, beds_max, property_types[], price_min, price_max}`), cron_schedule (nullable, reserved for v2), created_at.
- `scrape_list_suburb` — m2m, `(scrape_list_id, suburb_id)`.
- `property` — id, oth_property_id (unique, nullable), formatted_address, postcode, suburb_id, location (`geography(Point, 4326)`, nullable), first_seen_at. Unique secondary on `(formatted_address, postcode)`.
- `listing` — id, property_id, suburb_id, category (`forsale|forrent|recentlysold`), oth_listing_id (nullable), agent_name, agency_name, first_seen_at, last_seen_at, closed_at (nullable), closure_reason (nullable enum: `unknown|sold|withdrawn|expired`).
- `listing_snapshot` — id, listing_id, observed_at, price (int, AUD; for rent → weekly), title, blurb (nullable in v1), bedrooms, bathrooms, parking, land_size_sqm, property_type, status, raw_payload (JSONB), changed_fields (text[]).
- `scrape_job` — id, scrape_list_id (nullable for ad-hoc jobs), suburb_id, category, filters (JSONB, copied from list at enqueue), status (`queued|running|succeeded|failed|deadletter`), attempts, last_error_class, last_error_message, claimed_at, completed_at, created_at.

### API contracts

- `POST /scrape-lists` — create list with name + filters.
- `GET /scrape-lists`, `GET /scrape-lists/{id}` — list / detail.
- `PUT /scrape-lists/{id}` — update name, filters, suburbs.
- `POST /scrape-lists/{id}/suburbs` — add a suburb (resolves via autocomplete; if multiple matches, returns 409 with candidates).
- `DELETE /scrape-lists/{id}/suburbs/{suburb_id}` — remove.
- `POST /scrape-lists/{id}/run` — fan-out producer; returns the created job IDs.
- `GET /jobs?status=&list_id=` — list jobs.
- `GET /jobs/{id}` — job detail with error info.
- `GET /properties?suburb=&postcode=` — paginated property list.
- `GET /listings?suburb=&category=&active=true` — listings filtered.
- `GET /listings/{id}` — detail with current snapshot.
- `GET /listings/{id}/snapshots` — full history.

CLI mirrors: `oth suburb resolve`, `oth list create / show / run`, `oth jobs ls`, `oth listings ls / history`.

### Anti-bot interaction (encoded from grilling)

Worker startup and request loop:

```
on first job, or on rotation trigger:
    spawn camoufox (headless, randomised fingerprint)
    page.goto("https://www.onthehouse.com.au/")
    wait for any anti-bot challenge to settle (humanlike interaction)
    capture cookies + selected headers (UA, Accept-Language)
    instantiate httpx.AsyncClient with those cookies/headers

per request:
    rate_limiter.acquire("onthehouse.com.au")
    response = await httpx.post(SEARCH_URL, json=payload)
    if response.status in (403, 429) or "Cloudflare" in response.text:
        raise AntiBotError  # caught by worker → rebootstrap session
    if requests_since_bootstrap >= N or age >= T:
        schedule rotation before next request
```

### Job lifecycle

```
queued → running → succeeded
                 → failed (transient, attempts < 3) → queued
                 → failed (anti-bot, attempts < 1)  → queued (with rebootstrap signal)
                 → deadletter (parse error or attempts exhausted)
```

### Soft expiry

After every successful run of a `(suburb_id, category)`, the reconciler runs:

```sql
UPDATE listing
SET closed_at = NOW(), closure_reason = 'unknown'
WHERE suburb_id = :s AND category = :c
  AND closed_at IS NULL
  AND last_seen_at < NOW() - (:n_runs * :avg_run_interval);
```

The threshold (`n_runs`, `avg_run_interval`) is configurable; defaults pegged to "missed in 3 consecutive scrapes".

## Testing Decisions

A good test in this codebase exercises an external behaviour of a module — given input, observe output or recorded side effects — rather than asserting on private structure or call ordering. Tests should be fast, deterministic, and survive refactors that don't change behaviour.

### Modules with explicit unit-test coverage

- **Snapshot diff engine** — pure. Table-driven tests covering: no prior snapshot → `ChangedFields(all)`; identical observation → `None`; price change → `ChangedFields([price])`; blurb whitespace-only change → `None` (normalised); status flip ForSale→Sold → `ChangedFields([status, ...])`. Highest leverage for low effort.
- **OTH API client (parser)** — recorded JSON fixtures for each category (`forsale`, `forrent`, `recentlysold`) and edge cases (missing land size, no agent, multiple agents, weekly vs monthly rent). Asserts the parser produces the expected typed object. Catches OTH schema drift early; fixtures double as documentation.
- **Job queue** — integration tests against a real Postgres in a test container. Concurrency tests fire N tasks calling `claim_next()` simultaneously and assert each job is claimed exactly once. Tests retry counter increments, transitions through `failed` and `deadletter`, and that `complete` is idempotent under retries.
- **Rate limiter** — unit tests with a mockable monotonic clock. Asserts that requests are spaced ≥ min_interval, that jitter falls within the configured range, and that an idle bucket refills correctly.

### Other testing

- **Listing reconciler** — integration test: feed a fake OTH page result through the reconciler against a real Postgres test DB; assert Property/Listing/Snapshot rows are correct after one run, then re-run the same input and assert no new snapshot is written, then change a field and assert exactly one new snapshot.
- **FastAPI endpoints** — thin behaviour tests against an in-process app + test DB; one happy-path test per endpoint, plus the autocomplete-disambiguation 409 case.
- **Worker loop** — one integration test driving the full claim → reconcile → complete cycle with the OTH client mocked; one for the anti-bot retry path; one for the dead-letter path.
- **Live E2E smoke** — a single test gated behind `RUN_LIVE_OTH_TESTS=1` that scrapes one small suburb end-to-end against real OTH. Run manually before releases, never in CI.

### Prior art

The existing `services/property-scraper` has no tests — it's exploratory code. Test patterns (pytest + pytest-asyncio + httpx mock + a Postgres test container) are new to this repo and will be established by this service.

## Out of Scope

- **Detail-page enrichment** — visiting individual listing URLs to capture blurb / land size / auction date / photos. Deferred to v2. v1 captures only what the search API returns. Means: blurb may be empty for `ForSale`/`ForRent` listings in v1.
- **Two-pass closure resolution** — visiting missing-listing URLs to get a definitive `sold`/`withdrawn`/`expired` reason. v1 uses soft expiry only.
- **Scheduling** — the `cron_schedule` column exists on `ScrapeList` but no scheduler runs in v1; users (or external cron) hit the trigger endpoint manually.
- **Map UI / scrape-list drawing** — explicitly dropped from v1 by the user. Geo data is captured in PostGIS-ready form so a future UI can use it.
- **Frontend integration** — the existing `apps/frontend` is not modified. The new service exposes a REST API ready for future use but no UI consumes it yet.
- **Authentication / multi-user** — single-user, localhost-only.
- **Bathroom filter** — filters cover beds, property type, price range only.
- **Off-market / historical sales** — only `ForSale`, `ForRent`, `RecentlySold` (≤90d) categories.
- **Proxy rotation** — not implemented in v1; defer until anti-bot exposure forces it.
- **Production deployment** — local-only via docker-compose.
- **Migration of data from the existing `property-scraper`** — schemas are incompatible; old JSON files are archived but not loaded.

## Further Notes

- The existing `services/property-scraper/src/api_client.py` and the JS extractors in `services/property-scraper/js/` are the closest prior art for talking to OTH and parsing card markup. Port them as starting material; don't import them directly — the new service has different storage and concurrency assumptions.
- The "Compass" anti-bot technique referenced during grilling is on a separate project on the same machine. The school-scraper at `services/school-scraper/scraper.js` shows the playwright-extra-stealth + context rotation approach in JS; we apply the same shape with camoufox in Python.
- Hot-path metric to watch once running: ratio of HTTP-only responses to camoufox-rebootstraps. A high rebootstrap rate means OTH's anti-bot is detecting the httpx phase and the rotation interval needs tightening.
- The PostGIS extension is enabled in the first migration even though no v1 endpoint queries spatial data, to avoid a coordinated migration when the map UI is reintroduced.
