# CLAUDE.md — listings-scraper service

- **Design source of truth**: `docs/scraper-service/PRD.md` — the PRD plus 14 issue specs that built v1. Read this before making structural decisions.
- **Domain model reference**: `docs/scraper-service/DOMAIN_MODEL.md` — entities, fields, relationships, invariants, and common queries. Reference this in conversations about data shape.
- **Operational docs**: `services/listings-scraper/README.md` — how to bring up the docker-compose stack, run migrations, env vars (including anti-bot tuning knobs), and run the live E2E smoke test.

## Python style

- Python 3.11+. `from __future__ import annotations` is not needed (3.11 has deferred evaluation by default for string annotations via PEP 563 opt-in; we use direct type hints).
- Line length: 100 characters.
- Async everywhere in the service layer and DB layer. Use `asyncio.TaskGroup` for fan-out. Never `asyncio.gather` with bare exceptions silenced.
- Logging via `logging.getLogger(__name__)`. Log at `INFO` for job lifecycle events, `DEBUG` for per-request noise. Never log raw OTH JSON at INFO — it's noisy.
- Error handling: raise typed exceptions from deep modules (`AntiBotError`, `ParseError`, `TransientError`). Coordination modules catch and route. Do not swallow exceptions silently.
- `pydantic-settings` for all config. Env-var prefix transition: `LS_` is the new canonical prefix (PR 3), `OTH_` is the legacy prefix. Both are accepted via `AliasChoices`. New code and docs should use `LS_*`. No `os.environ` direct reads in business logic.

## Architecture (from PRD)

Two categories of modules:

**Deep modules** — testable in isolation, narrow interfaces, no cross-dependencies:
- `vendor_resolvers/oth` — OTH autocomplete → `ResolvedSuburb`
- `vendor_resolvers/domain` — deterministic Domain slug builder → `ResolvedSuburb` (requires postcode + state; no network call)
- `vendor_clients/oth` — Pydantic models for OTH search request/response, no DB knowledge
- `vendor_clients/domain` — camoufox-based Domain search via `__NEXT_DATA__` extraction; uses `session.page()` not `session.http()`
- `price_normaliser` — vendor-neutral price string classifier; supports both OTH and Domain price formats (M/k suffix, "Offers over", etc.)
- `scrape_session` — camoufox lifecycle, cookie capture, httpx reuse, rotation. `page()` method (PR 3) provides a fresh camoufox Page for Domain fetches.
- `snapshot_diff` — pure function: `diff(prev, new) → ChangedFields | None`
- `job_queue` — Postgres-backed queue with `SKIP LOCKED`
- `rate_limiter` — token bucket, async-aware

**Coordination modules** — wire deep modules together:
- `listing_reconciler` — upsert Property/Listing/Snapshot, run soft-expiry sweep
- `scrape_list_service` — CRUD + fan-out
- `worker_loop` — claim → VendorRegistry dispatch → paginate → reconcile → complete. VendorRegistry maps `Vendor` → `(client, session)` pair so OTH and Domain use separate sessions.
- `api/app.py` + `cli/main.py` — both call service layer only, never deep modules directly

**Rule**: coordination modules may import deep modules. Deep modules must not import each other or coordination modules.

## Domain vendor support (PR 3)

Domain.com.au uses Next.js SSR — search results are embedded as `__NEXT_DATA__` JSON in the page HTML. There is no separate XHR endpoint.

**Fetch flow** (Domain only):
1. `DomainApiClient.search()` calls `session.page()` to get a fresh camoufox Page.
2. Navigates to `https://www.domain.com.au/{sale|rent|sold}/{suburb-slug}/?page=N`.
3. Reads `page.content()` for the rendered HTML.
4. `extract_next_data(html)` finds `<script id="__NEXT_DATA__">` and parses the JSON.
5. `parse_next_data_listings()` extracts `listingsMap[id].listingModel` entries and maps them to `VendorListing`.

**Akamai anti-bot** (`configs/domain.py`):
- HTTP 429 → `AntiBotError`
- HTTP 200 with body < 5 KB → `AntiBotError` (challenge page)
- Cookie `_abck` containing `~-1~` → `AntiBotError` (Akamai bot verdict)

**ScrapeSession.page()** (`session.py`):
- Lazily boots a separate camoufox browser context on first call.
- The context is reused for the session lifetime (Akamai session continuity).
- Rotation tears down both the httpx client AND the browser context.
- OTH uses `session.http()` (unchanged). Domain uses `session.page()`.
- Design choice: separate browser lifecycle from the httpx bootstrap. Both share rotation counters.

**Domain suburb slug format**: `<name-lowercased-hyphenated>-<state-lower>-<postcode>`
e.g. `paddington-qld-4064`. `DomainSuburbResolver` requires both `postcode` and `state`.

**V1 limitations** (URL filters not yet applied):
- Domain URL filters (bedrooms, price range, property type) are NOT yet encoded in search URLs.
- The worker fetches all listings from Domain's paginated feed and stores them unfiltered.
- TODO(pr-after-3): add URL-level filter query-parameter support for Domain searches.

**Status tag policy**:
- Only `"Under offer"` and `"Sold"` tags (case-insensitive) influence the `status` field.
- `"New"` and `"Updated"` tags are deliberately ignored — they are Domain cache-freshness
  noise that would cause snapshot churn without any meaningful state change.

## Database

- SQLAlchemy 2.0 async. All queries via `AsyncSession`. Never use sync session.
- Alembic for all schema changes. One migration per PR that touches schema. Migration file name format: `NNNN_short_description.py`.
- `Base` is defined in `src/listings_scraper/db/engine.py`. All models import from there.
- Models live in `src/listings_scraper/db/models/`. One file per domain concept.

## Testing

- `pytest` + `pytest-asyncio` (mode=auto). All async test functions are auto-detected.
- Deep modules get unit tests. Coordination modules get integration tests against a real Postgres test container.
- OTH JSON fixtures live in `tests/fixtures/oth/`. Domain fixtures live in `tests/fixtures/domain/`. Never inline vendor JSON in test code.
- `httpx.MockTransport` (via `inner_transport=` injection on `ScrapeSession`) for mocking HTTP in OTH client tests.
- Live E2E tests: gated behind env vars. OTH: `RUN_LIVE_OTH_TESTS=1`. Domain: `RUN_LIVE_DOMAIN_TESTS=1`. Never run in CI.
- Do not test private methods. Test observable behaviour: given input → assert output or DB state.

## Key invariants

- The API and CLI must call identical service-layer functions. If you add a REST endpoint, add the matching CLI command in the same PR.
- `snapshot_diff` is pure — no I/O, no DB, no side effects. Keep it that way.
- Workers claim jobs via `SELECT ... FOR UPDATE SKIP LOCKED`. Never claim outside that pattern.
- The `raw_payload` JSONB column on `listing_snapshot` is write-once. Never update it after insert.
