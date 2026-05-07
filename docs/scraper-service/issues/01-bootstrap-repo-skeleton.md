# 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic

## What to build

Stand up the scaffolding the rest of the work plugs into. Create `services/oth-scraper` as a fresh Python project (uv-managed, Python 3.11+) with FastAPI and Typer entrypoints, an empty service layer, and a `docker-compose.yml` that brings up `api`, `worker`, and `postgres` (Postgres 16 with the PostGIS extension installed). Wire SQLAlchemy 2.0 async + Alembic; produce the first migration enabling the `postgis` extension and creating an empty schema (no tables yet — those land with the modules that own them). The service binds to `127.0.0.1`. The worker container starts and immediately idles — the actual loop arrives in a later slice.

Existing prior art lives in `services/property-scraper/` (Python uv setup, Taskfile pattern). Follow the same Taskfile + uv conventions; register the new service in the root `Taskfile.yml`.

## Acceptance criteria

- [ ] `docker compose up` from `services/oth-scraper/` brings up Postgres, api, and worker without errors.
- [ ] `curl http://127.0.0.1:<port>/health` returns 200 from the api container.
- [ ] The api container refuses connections from anything other than 127.0.0.1.
- [ ] `alembic upgrade head` runs cleanly and enables the `postgis` extension; `SELECT PostGIS_Version();` succeeds.
- [ ] `uv run pytest` runs (zero tests pass, but the harness is wired).
- [ ] Root `Taskfile.yml` has an `oth-scraper:install` task and the install entry registers it.
- [ ] `worker` container starts, logs that it has no work to do, and stays alive.
- [ ] Same Docker image is used for `api` and `worker`; only the entrypoint differs.
- [ ] `services/oth-scraper/README.md` exists and documents: how to start the stack (`docker compose up`), how to run migrations, how to run the test suite, env vars consumed by api and worker, and how to tear down. Should be readable as the first thing a new contributor sees.
- [ ] `services/oth-scraper/CLAUDE.md` exists and documents conventions for future Claude/agent work in this service: Python style (line length, async patterns, error handling, log style), the layered architecture (deep modules vs coordination modules per the PRD), test-fixture conventions, where to find OTH JSON fixtures (`tests/fixtures/oth/`), and a pointer to `docs/scraper-service/PRD.md` as the source of truth.

## Blocked by

None — can start immediately.
