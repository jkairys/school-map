# 12 — Producer fan-out + read API endpoints

## What to build

The user-facing entrypoint that turns "run this list" into queued jobs, plus the read endpoints needed to inspect what's happening.

**Producer**: `POST /scrape-lists/{id}/run`

- Loads the list and its suburbs.
- For each suburb × each of `[ForSale, ForRent, RecentlySold]`, enqueues one `ScrapeJob`. The job carries the list's filters snapshotted into `scrape_job.filters` (so editing the list later doesn't mutate in-flight jobs' provenance).
- Returns `{ "list_id": ..., "job_ids": [...], "count": N }`.

**Read endpoints**:

- `GET /jobs?status=&list_id=` — paginated, filterable.
- `GET /jobs/{id}` — single job with full error info if any.
- `GET /properties?suburb=&postcode=` — paginated property list.
- `GET /listings?suburb=&category=&active=true` — listings with optional active filter (`closed_at IS NULL`).
- `GET /listings/{id}` — listing detail with the latest snapshot embedded.
- `GET /listings/{id}/snapshots` — full snapshot history for one listing.

All read endpoints support pagination via `?limit=` and `?cursor=` (or `?offset=`, pick whichever is simplest given SQLAlchemy 2.0 patterns).

## Acceptance criteria

- [ ] `POST /scrape-lists/{id}/run` against a 3-suburb list creates exactly 9 queued jobs.
- [ ] Jobs carry the snapshotted filters from the list at enqueue time; editing the list afterwards doesn't change them.
- [ ] Each read endpoint returns the documented shape, verified by an httpx-against-test-app integration test.
- [ ] An end-to-end happy-path test: create list → add suburb → run → wait for worker (in the same process for the test) → assert listings/snapshots are queryable via the read API.
- [ ] All endpoints documented in the auto-generated OpenAPI spec at `/docs`.

## Blocked by

- 03 — ScrapeList CRUD with filter validation
- 11 — Worker loop with tiered retry and dead-letter
