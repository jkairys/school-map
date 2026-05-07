# 02 — Suburb resolver via OTH autocomplete

## What to build

A deep module that turns a free-text suburb name (e.g. `"Little Mountain"`) into a resolved `(name, postcode, state, oth_slug)` tuple, using OTH's location-autocomplete endpoint as the source of truth, and caches the result in a new `suburb` table.

The module exposes one function:

```
async def resolve(name: str) -> ResolvedSuburb | list[Match]
```

A single confident match returns `ResolvedSuburb` and persists a row. Multiple matches return the candidate list; the caller (REST endpoint or CLI) is responsible for prompting the user.

Wire this into both surfaces:

- `POST /suburbs/resolve` — body `{ "name": "..." }`. Returns 200 with a resolved row, or 409 with a candidate list when ambiguous. Idempotent: a second call for an already-cached suburb returns the cached row without hitting OTH.
- `oth suburb resolve <name>` — CLI prints the resolved row, or prompts to pick when ambiguous.

The HTTP call to OTH should go through a generic httpx client (no anti-bot session needed for autocomplete — verify this assumption empirically and document the result in the PR; if anti-bot is in fact required, raise it as a follow-up rather than expanding scope here).

## Acceptance criteria

- [ ] `suburb` table created via Alembic migration: `id`, `name`, `postcode`, `state`, `oth_slug`, `resolved_at`. Unique constraint on `(name, postcode, state)`.
- [ ] `resolve("Little Mountain")` returns a `ResolvedSuburb` for QLD 4551.
- [ ] `resolve("Richmond")` returns a list of matches (multiple states).
- [ ] Repeated calls for a cached suburb hit the DB only — no OTH request.
- [ ] `POST /suburbs/resolve` returns 200 / 409 as described.
- [ ] CLI command works end-to-end against a live OTH autocomplete (recorded fixture sufficient for tests).
- [ ] Unit tests cover: single-match parsing, multi-match parsing, malformed response handling.

## Blocked by

- 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic
