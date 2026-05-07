# 05 — OTH API client (request builder + parser)

## What to build

A deep module that knows everything about OTH's search API and nothing about the database. It exposes:

```
class OTHApiClient:
    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,        # forsale | forrent | recentlysold
        filters: ListingFilters,
        page: int,
        http: httpx.AsyncClient,   # caller-supplied; client reuses its cookies/headers
    ) -> SearchPage:
        ...
```

`SearchPage` is a Pydantic model carrying a list of `OTHListing` (typed; covers all fields the snapshot schema cares about) plus pagination metadata (`total`, `page`, `has_next`).

The module:

- Builds the JSON payload for `POST https://www.onthehouse.com.au/odin/api/composite/search` for any of the 3 categories. Honours filter dimensions: bedroom min/max, property types (multi-select), price min/max.
- Parses the response into typed objects, including extraction of: oth_property_id, formatted_address, postcode, lat/lon (when present), beds, baths, parking, land_size_sqm, property_type, agent_name, agency_name, listing url, status, price (sale price for sold, asking price for forsale, weekly rent for forrent), title.
- Handles missing fields gracefully (lat/lon especially, often missing for older sold listings).
- Does NOT manage the httpx client — the caller passes one in. This separation lets issue 10 inject the camoufox-bootstrapped client.

Recorded fixtures live under `tests/fixtures/oth/` — at least one per category and a few edge cases (rental with weekly+monthly rent fields, sold without land size, multiple agents).

### Fixture capture (HITL one-off)

The repo has no real OTH fixtures committed yet. Before writing the parser, capture the canonical dataset that the parser tests will run against:

1. Add a small ad-hoc script `services/oth-scraper/scripts/capture_fixtures.py` that uses bare Playwright (NOT camoufox — that comes in issue 10) to load `https://www.onthehouse.com.au/` once, then makes 3 search calls via `page.evaluate(fetch(...))` for one suburb, one per category: `ForSale`, `ForRent`, `RecentlySold`. Pick a suburb known to have listings in all three (e.g. Paddington QLD 4064).
2. Save raw responses to `services/oth-scraper/tests/fixtures/oth/{category}_paddington_p0.json`.
3. Manually run the script once; commit the JSON outputs to the repo.
4. Eyeball each fixture: confirm it contains at least one listing with land size, one without, and (for `ForRent`) the weekly-rent field shape so the parser tests can cover those edge cases. If gaps, capture additional fixtures from another suburb (e.g. Bondi NSW for variety) or another page.
5. The script is committed but not run in CI.

The actual parser implementation work is AFK once fixtures exist.

## Acceptance criteria

- [ ] Request builder produces the correct payload for each of the 3 categories — verified by snapshot test against committed expected payloads.
- [ ] Parser converts each fixture file into the expected `SearchPage` — table-driven test.
- [ ] Edge cases covered: missing land size → `None`, missing lat/lon → `None`, multiple agents → first agent name, weekly rent string parsed to int.
- [ ] Filters propagate correctly: `beds_min/max` map to OTH's bed range, `property_types` to the type filter, `price_min/max` to the appropriate price filter (different field per category).
- [ ] No DB access anywhere in this module — verified by import-time assertion or a lint rule.

## Blocked by

- 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic

## Type

HITL — fixture capture is a one-off developer step. The parser implementation that follows is AFK.
