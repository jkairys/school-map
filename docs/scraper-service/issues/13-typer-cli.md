# 13 — Typer CLI mirroring REST endpoints

## What to build

A Typer-based CLI (`oth ...`) that wraps the same service-layer functions the REST API uses. Both surfaces share the implementation; if a behaviour is correct via REST it's correct via CLI.

Commands:

- `oth suburb resolve <name>` — interactive disambiguation if multiple matches.
- `oth list create <name> [--filters @file.json]`
- `oth list ls`
- `oth list show <id-or-name>`
- `oth list update <id-or-name> [--name] [--filters @file.json]`
- `oth list add-suburb <list> <suburb-name>` — interactive disambiguation.
- `oth list rm-suburb <list> <suburb-id-or-name>`
- `oth list rm <id-or-name>`
- `oth list run <id-or-name>` — kicks off the producer.
- `oth jobs ls [--status] [--list]`
- `oth jobs show <id>`
- `oth listings ls [--suburb] [--category] [--active]`
- `oth listings show <id>`
- `oth listings history <id>` — prints snapshot history.
- `oth dev session-smoke` — already added in issue 10.

The CLI reads the API base URL from env (`OTH_SCRAPER_BASE_URL`, default `http://127.0.0.1:8000`) and talks to the running service over HTTP — it does NOT bypass the API and connect to Postgres directly. That keeps the surfaces consistent and tests one path.

## Acceptance criteria

- [ ] All commands listed above exist and call the corresponding REST endpoints.
- [ ] `oth list run` returns the count of queued jobs.
- [ ] Disambiguation prompts work in a TTY; in non-TTY mode (CI/script), `--postcode` and `--state` flags can be passed to disambiguate non-interactively.
- [ ] Integration test runs the CLI as a subprocess against a running test app and asserts output for one happy-path command per area.
- [ ] CLI and REST are wired into the same Docker image; running `docker compose exec api oth list ls` works.

## Blocked by

- 12 — Producer fan-out + read API endpoints
