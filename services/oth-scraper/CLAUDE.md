# CLAUDE.md — oth-scraper service

- **Design source of truth**: `docs/scraper-service/PRD.md` — the PRD plus 14 issue specs that built v1. Read this before making structural decisions.
- **Domain model reference**: `docs/scraper-service/DOMAIN_MODEL.md` — entities, fields, relationships, invariants, and common queries. Reference this in conversations about data shape.
- **Operational docs**: `services/oth-scraper/README.md` — how to bring up the docker-compose stack, run migrations, env vars (including anti-bot tuning knobs), and run the live E2E smoke test.

## Python style

- Python 3.11+. `from __future__ import annotations` is not needed (3.11 has deferred evaluation by default for string annotations via PEP 563 opt-in; we use direct type hints).
- Line length: 100 characters.
- Async everywhere in the service layer and DB layer. Use `asyncio.TaskGroup` for fan-out. Never `asyncio.gather` with bare exceptions silenced.
- Logging via `logging.getLogger(__name__)`. Log at `INFO` for job lifecycle events, `DEBUG` for per-request noise. Never log raw OTH JSON at INFO — it's noisy.
- Error handling: raise typed exceptions from deep modules (`AntiBotError`, `ParseError`, `TransientError`). Coordination modules catch and route. Do not swallow exceptions silently.
- `pydantic-settings` for all config. All env vars prefixed `OTH_`. No `os.environ` direct reads in business logic.

## Architecture (from PRD)

Two categories of modules:

**Deep modules** — testable in isolation, narrow interfaces, no cross-dependencies:
- `suburb_resolver` — OTH autocomplete → `ResolvedSuburb`
- `oth_client` — Pydantic models for OTH search request/response, no DB knowledge
- `scrape_session` — camoufox lifecycle, cookie capture, httpx reuse, rotation
- `snapshot_diff` — pure function: `diff(prev, new) → ChangedFields | None`
- `job_queue` — Postgres-backed queue with `SKIP LOCKED`
- `rate_limiter` — token bucket, async-aware

**Coordination modules** — wire deep modules together:
- `listing_reconciler` — upsert Property/Listing/Snapshot, run soft-expiry sweep
- `scrape_list_service` — CRUD + fan-out
- `worker_loop` — claim → session → paginate OTH → reconcile → complete
- `api/app.py` + `cli/main.py` — both call service layer only, never deep modules directly

**Rule**: coordination modules may import deep modules. Deep modules must not import each other or coordination modules.

## Database

- SQLAlchemy 2.0 async. All queries via `AsyncSession`. Never use sync session.
- Alembic for all schema changes. One migration per PR that touches schema. Migration file name format: `NNNN_short_description.py`.
- `Base` is defined in `src/oth_scraper/db/engine.py`. All models import from there.
- Models live in `src/oth_scraper/db/models/`. One file per domain concept.

## Testing

- `pytest` + `pytest-asyncio` (mode=auto). All async test functions are auto-detected.
- Deep modules get unit tests. Coordination modules get integration tests against a real Postgres test container.
- OTH JSON fixtures live in `tests/fixtures/oth/`. File names encode category and edge case: `forsale_standard.json`, `forrent_weekly_rent.json`, `recentlysold_no_agent.json`, etc. Never inline OTH JSON in test code.
- `pytest-httpx` for mocking `httpx.AsyncClient` in OTH client tests.
- Live E2E tests: single file `tests/test_live_e2e.py`, all tests gated behind `RUN_LIVE_OTH_TESTS=1`. Never run in CI.
- Do not test private methods. Test observable behaviour: given input → assert output or DB state.

## Key invariants

- The API and CLI must call identical service-layer functions. If you add a REST endpoint, add the matching CLI command in the same PR.
- `snapshot_diff` is pure — no I/O, no DB, no side effects. Keep it that way.
- Workers claim jobs via `SELECT ... FOR UPDATE SKIP LOCKED`. Never claim outside that pattern.
- The `raw_payload` JSONB column on `listing_snapshot` is write-once. Never update it after insert.
