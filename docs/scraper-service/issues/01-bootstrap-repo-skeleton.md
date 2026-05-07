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

## Blocked by

None — can start immediately.
