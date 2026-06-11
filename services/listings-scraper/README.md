# listings-scraper

A multi-vendor microservice for tracking Australian residential real estate listings (onthehouse.com.au and domain.com.au).

## Quick start

```bash
# From services/listings-scraper/
docker compose up --build
```

This starts three containers: `api` (FastAPI on port 8000), `worker` (idle loop), `postgres` (Postgres 16 + PostGIS).

The API is reachable only from localhost:

```bash
curl http://127.0.0.1:8000/health
# {"status": "ok"}
```

## Run migrations

Migrations run against the Postgres container. With the stack up:

```bash
# From services/listings-scraper/
docker compose exec api uv run alembic upgrade head
```

Or locally against a running Postgres (adjust DATABASE_URL):

```bash
export OTH_DATABASE_URL=postgresql+asyncpg://oth:oth@localhost:5432/oth
uv run alembic upgrade head
```

Verify PostGIS is enabled:

```bash
docker compose exec postgres psql -U oth -d oth -c "SELECT PostGIS_Version();"
```

## Run the test suite

```bash
uv run pytest
# or via Taskfile:
task test
```

Zero tests pass in the bootstrap skeleton — the harness is wired and ready for later issues.

## Environment variables

All variables are prefixed `OTH_`. Copy `.env.example` to `.env` for local-only (non-Docker) runs.

| Variable | Default | Description |
|---|---|---|
| `OTH_DATABASE_URL` | `postgresql+asyncpg://oth:oth@localhost:5432/oth` | Async SQLAlchemy DSN |
| `OTH_API_HOST` | `127.0.0.1` | Bind address (set to `0.0.0.0` inside Docker) |
| `OTH_API_PORT` | `8000` | API listen port |
| `OTH_WORKER_CONCURRENCY` | `2` | Number of concurrent worker tasks |
| `OTH_SESSION_MAX_REQUESTS` | `50` | Requests before camoufox session rotates |
| `OTH_SESSION_MAX_AGE_SECONDS` | `1800` | Age (seconds) before camoufox session rotates |
| `OTH_RATE_LIMIT_MIN_INTERVAL` | `1.5` | Minimum seconds between OTH requests |
| `OTH_RATE_LIMIT_MAX_INTERVAL` | `3.0` | Maximum seconds between OTH requests (jitter cap) |
| `OTH_SOFT_EXPIRY_DAYS` | `14` | Days a listing must be unseen in its `(suburb, category)` feed before the soft-expiry sweep closes it (`closure_reason='unknown'`). 14d covers ~3 missed daily scrapes. |
| `OTH_QUEUE_RETRY_MAX_TRANSIENT` | `3` | Max retries for transient errors (5xx/timeout) before dead-letter |
| `OTH_QUEUE_RETRY_MAX_ANTIBOT` | `1` | Max retries for anti-bot errors (403/429/Cloudflare) before dead-letter |
| `OTH_QUEUE_RETRY_MAX_PARSE` | `0` | Max retries for parse errors before dead-letter (0 = immediate) |
| `OTH_QUEUE_RECLAIM_TTL_SECONDS` | `600` | A `running` job older than this is re-claimable by `claim_next()` |

## Live E2E smoke test

A single end-to-end test at `tests/e2e/test_live_smoke.py` exercises the
producer → worker → read-API path against **real OTH** for one small
suburb (Mount Coolum QLD). It is skipped by default and only runs when
`RUN_LIVE_OTH_TESTS=1`. **It does not run in CI** — there is no CI
configuration in this repository today, and the env-var gate keeps it
skipped even if `uv run pytest` is executed there in the future. Treat
it as the developer's responsibility to run before merging changes that
touch the scrape session, OTH API client, or worker loop.

Run it with stdout visible (the test prints job statuses + last errors
on failure, which is what you want at release time):

```bash
RUN_LIVE_OTH_TESTS=1 uv run pytest \
    services/listings-scraper/tests/e2e/test_live_smoke.py -s
```

Requires Docker (Postgres testcontainer) and a working camoufox
install (`uv sync` + `uv run playwright install firefox`).

### What anti-bot failure looks like

If OTH is blocking you, the per-job diagnostic block printed at the
end of the run will show jobs in `deadletter` with
`last_error_class=antibot` and a `last_error_message` like:

- HTTP **403** or **429** from `https://www.onthehouse.com.au/...`
- A sentinel string match in the body, e.g. `'Just a moment'`,
  `'Checking your browser'`, `'Attention Required! | Cloudflare'`,
  `'_Incapsula_Resource'`.

Knobs to consider tuning when this happens (all `OTH_`-prefixed):

| Variable | Effect |
|---|---|
| `OTH_SESSION_MAX_REQUESTS` | Rotate camoufox after this many requests (default `50`). Lower it to rotate more aggressively. |
| `OTH_SESSION_MAX_AGE_SECONDS` | Rotate camoufox after this many seconds (default `1800`). Lower it for shorter session lifetimes. |
| `OTH_RATE_LIMIT_MIN_INTERVAL` / `OTH_RATE_LIMIT_MAX_INTERVAL` | Slow the request cadence (defaults `1.5` / `3.0` seconds). |
| `OTH_QUEUE_RETRY_MAX_ANTIBOT` | Number of anti-bot retries before dead-letter (default `1`). |

If anti-bot keeps tripping after rotation, capture an example
response (status + body snippet) and revisit the camoufox bootstrap in
`src/listings_scraper/scrape_session/`.

## Tear down

```bash
# Stop containers and delete volumes (including Postgres data):
docker compose down -v
```

## Project layout

```
services/listings-scraper/
├── src/listings_scraper/
│   ├── api/          # FastAPI app + uvicorn entrypoint
│   ├── cli/          # Typer CLI (mirrors REST endpoints)
│   ├── db/           # SQLAlchemy engine, Base, session factory
│   ├── services/     # Service layer (shared by API and CLI)
│   ├── config.py     # pydantic-settings configuration
│   └── worker.py     # Worker entrypoint (idle in v1)
├── alembic/          # Alembic migrations
├── tests/
│   └── fixtures/oth/ # Recorded OTH JSON fixtures (populated in issue 02/05)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Taskfile.yml
```
