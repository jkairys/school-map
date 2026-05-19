# Multi-vendor scraper refactor — plan

## Summary

Refactor `services/oth-scraper/` into `services/listings-scraper/`, a vendor-agnostic listings scraper that drives both onthehouse.com.au and domain.com.au from one queue, one DB schema, and one worker. Vendor-specific code is isolated behind `VendorClient` and `VendorSuburbResolver` interfaces; the `scrape_session` deep module is reparameterised by `BootstrapConfig` and a pluggable anti-bot detector. The existing OTH dataset (113 suburbs / 9,665 properties / 9,693 snapshots) survives via a `source` enum column populated to `'oth'` for all legacy rows, plus column renames (`oth_*` → `external_*` + `source`). Detail-page fetches stay out of scope; only search-list data is captured. Delivered as **3 sequential PRs**, each independently mergeable and non-breaking for the running OTH worker.

## Target architecture

### Service rename and module layout

```
services/listings-scraper/
└── src/listings_scraper/
    ├── config.py                       # env prefix LS_, falls back to OTH_ during transition
    ├── worker.py
    ├── snapshot_diff.py                # UNCHANGED (pure)
    ├── db/
    │   ├── engine.py
    │   └── models/                     # neutralised; see Domain model changes
    ├── vendor.py                       # Vendor enum + protocol re-exports
    ├── vendor_clients/
    │   ├── base.py                     # VendorClient Protocol, VendorListing model
    │   ├── oth/
    │   │   ├── client.py               # was oth_client/client.py
    │   │   ├── payload.py
    │   │   ├── parser.py               # OTH JSON → VendorListing
    │   │   └── types.py                # OTH-internal models only
    │   └── domain/
    │       ├── client.py               # uses scrape_session.page() instead of httpx.post
    │       ├── next_data.py            # __NEXT_DATA__ extraction
    │       └── parser.py               # listingsMap[id].listingModel → VendorListing
    ├── vendor_resolvers/
    │   ├── base.py                     # VendorSuburbResolver Protocol
    │   ├── oth/resolver.py             # was suburb_resolver/
    │   └── domain/resolver.py          # string-template based
    ├── price_normaliser/               # NEW deep module
    │   ├── __init__.py
    │   ├── types.py                    # PriceKind enum, NormalisedPrice
    │   └── parser.py                   # tested against fixtures
    ├── scrape_session/
    │   ├── session.py                  # accepts BootstrapConfig + AntiBotDetector
    │   ├── bootstrap.py                # AsyncCamoufox lifecycle (vendor-neutral)
    │   ├── configs/oth.py              # OTH BootstrapConfig + sentinel detector
    │   └── configs/domain.py           # Domain BootstrapConfig + Akamai detector
    ├── listing_reconciler/             # upserts by (source, external_property_id)
    ├── queue/                          # UNCHANGED
    ├── rate_limiter/                   # UNCHANGED
    ├── worker_loop/loop.py             # dispatches by job.source
    ├── services/                       # CRUD: scrape_list, suburb (each carries source)
    ├── cli/                            # `scraper` entrypoint; subcommands by source
    └── api/                            # endpoints renamed to /v1/...; old unversioned paths kept as aliases for one release
```

### Vendor abstraction — signatures

```python
# vendor.py
class Vendor(str, Enum):
    OTH = "oth"
    DOMAIN = "domain"
```

```python
# vendor_clients/base.py
class VendorListing(BaseModel):
    model_config = ConfigDict(frozen=True)
    # identity
    source: Vendor
    external_listing_id: str        # campaign-level (OTH listing id, Domain int id)
    external_property_id: str | None  # OTH property id; for Domain == external_listing_id
    listing_url: str | None         # canonical detail URL
    # address
    formatted_address: str
    postcode: str
    state: str | None
    suburb_name: str | None
    latitude: float | None
    longitude: float | None
    coords_are_approximate: bool = False
    # features
    bedrooms: int | None
    bathrooms: int | None
    parking: int | None
    land_size_sqm: float | None
    property_type: str | None
    # marketing
    title: str | None
    status: str | None              # vendor-normalised status string
    agent_name: str | None
    agency_name: str | None
    # price
    raw_price_display: str | None   # free-form display string (always populated)
    price: int | None               # parsed numeric, may be NULL
    price_high: int | None          # for ranges/guides
    price_kind: PriceKind           # enum: PRICE/RANGE/AUCTION/EOI/CONTACT/RENT_WEEKLY/UNKNOWN
    observed_at: datetime

class SearchPage(BaseModel):
    listings: list[VendorListing]
    raw_payloads: list[dict]        # parallel; stored on snapshot.raw_payload
    page: int                       # 0-indexed
    has_next: bool
    total: int | None = None

class VendorClient(Protocol):
    source: Vendor
    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,
        filters: ListingFilters,
        page: int,
        session: ScrapeSession,
    ) -> SearchPage: ...
```

Note the contract change: OTH today receives an `httpx.AsyncClient` directly; the new signature accepts the `ScrapeSession`. OTH still pulls `await session.http()` internally; Domain pulls `await session.page()` (a new method that hands back a navigated camoufox page). This keeps both clients honest about who owns the transport.

```python
# vendor_resolvers/base.py
class VendorSuburbResolver(Protocol):
    source: Vendor
    async def resolve(
        self,
        name: str,
        *,
        db: AsyncSession,
        postcode: str | None = None,
        state: str | None = None,
    ) -> ResolvedSuburb | list[Match]: ...
```

`ResolvedSuburb` becomes vendor-neutral: `name, postcode, state, slug` plus the `source` it was resolved under. The `Suburb` model gains `source` + `slug` columns (see migration).

`Vendor` lives in `listings_scraper.vendor`; `vendor_clients.base`, `vendor_resolvers.base`, `db.models`, and `worker_loop` all depend on it. Deep modules import only `Vendor` and the base protocols — never each other's implementations.

### scrape_session changes

```python
@dataclass(frozen=True)
class BootstrapConfig:
    origin: str
    host: str
    bootstrap_url: str                  # home/landing to warm cookies
    bootstrap_fn: BootstrapFn           # captures cookies+UA+lang
    anti_bot_detector: AntiBotDetector
    max_requests: int
    max_age_seconds: int

class AntiBotDetector(Protocol):
    def check_response(self, response: httpx.Response) -> None: ...   # raises AntiBotError
    def check_page(self, body_text: str, cookies: dict[str, str]) -> None: ...
```

`configs/oth.py` keeps the existing `_SENTINEL_STRINGS` + 403/429 logic.
`configs/domain.py` checks `status != 200`, body length floor (~10 KB), and `_abck` containing `~-1~` (Akamai's "this is a bot" verdict).

A new method `ScrapeSession.page() -> camoufox.Page` is needed for Domain (the Next.js payload is in the HTML, not behind an XHR). It can lazily reuse the same warm camoufox context the bootstrap already opens — the spike confirmed that's safe and Akamai-friendly.

## Domain model changes

### Decision: option (b) `source` enum + single `external_id` columns

Rationale:
- Each vendor row in `property` / `listing` only ever has one external ID set. Per-source columns leave one NULL forever.
- Same physical property listed on both OTH and Domain becomes two `property` rows with distinct `(source, external_property_id)`. **Cross-vendor dedup is explicitly deferred** — flagged as an open question, not solved here.
- Indexes are simpler: one composite `(source, external_property_id)` unique index covers both vendors.

### Table-level diffs

**`suburb`**
- ADD `source` enum `vendor` NOT NULL (default `'oth'` during migration; default dropped after backfill)
- RENAME `oth_slug` → `slug` (semantics: vendor-specific URL slug fragment)
- UNIQUE `(source, name, postcode, state)` replaces `(name, postcode, state)`
- Domain `slug` is e.g. `"paddington-qld-4064"`; OTH stays `"paddington-4064"` style. Both are computable from `(name, state, postcode)` if needed but we cache anyway.

**`property`**
- ADD `source` enum NOT NULL default `'oth'`
- RENAME `oth_property_id` → `external_property_id` (nullable)
- DROP UNIQUE on `oth_property_id`; ADD UNIQUE `(source, external_property_id)` partial WHERE NOT NULL
- KEEP UNIQUE `(formatted_address, postcode)` but scope to `(source, formatted_address, postcode)` to avoid OTH↔Domain collisions in v1
- Reconciler upsert order: `(source, external_property_id)` → `(source, formatted_address, postcode)`

**`listing`**
- ADD `source` enum NOT NULL default `'oth'`
- RENAME `oth_listing_id` → `external_listing_id`
- UNIQUE on `(source, external_listing_id)` partial WHERE NOT NULL — Domain has stable int IDs we'll want to dedupe by
- Hot lookup index stays `(property_id, suburb_id, category) WHERE closed_at IS NULL` (already neutral)

**`listing_snapshot`**
- KEEP `price` (int, nullable) — back-compat
- ADD `price_display` text NULLABLE — the raw vendor string
- ADD `price_high` int NULLABLE — for ranges/guides
- ADD `price_kind` enum (`price`, `range`, `auction`, `eoi`, `contact`, `rent_weekly`, `unknown`) NULLABLE; backfilled to `price` for OTH rows where price IS NOT NULL, `unknown` where NULL
- `raw_payload` JSONB stays write-once. For Domain, this is the `listingsMap[id].listingModel` dict.
- Material fields list gets `price_kind` and `price_display` added to the diff allow-list (so a transition from `"For Sale"` → `"Auction"` registers as a change even if numeric `price` stays NULL).

**`scrape_job`**
- ADD `source` enum NOT NULL default `'oth'`
- `category` stays the same string column with values `forsale`/`forrent`/`recentlysold`. The Domain client translates: `forsale → /sale/`, `forrent → /rent/`, `recentlysold → /sold/`. This decision keeps the enum stable and avoids touching the queue/reclaim logic.

**`scrape_list`**
- ADD `source` enum NOT NULL default `'oth'` — a list runs against ONE vendor. If the user wants both, they create two lists. This matches the user's hint and keeps fan-out trivial.
- ADD `categories` JSONB defaulting to `["forsale","forrent","recentlysold"]` (move the implicit fan-out into data).

**`scrape_list_suburb`**
- No change; the m2m is vendor-implicit through the list and the suburb.
- Add a CHECK constraint or app-layer guard that `suburb.source == scrape_list.source` for every linked row. Easiest: validate in `services/scrape_list.py`.

### Price representation

A vendor-neutral `NormalisedPrice` value object lives in the new `price_normaliser/` deep module:

```python
class PriceKind(str, Enum):
    PRICE = "price"
    RANGE = "range"
    AUCTION = "auction"
    EOI = "eoi"
    CONTACT = "contact"
    RENT_WEEKLY = "rent_weekly"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class NormalisedPrice:
    kind: PriceKind
    low: int | None
    high: int | None
    display: str | None   # the original string

def normalise(display: str | None, category: Category) -> NormalisedPrice: ...
```

OTH's existing parsing logic moves into `price_normaliser.parse_oth_listing()` (uses the existing `_DOLLAR_AMOUNT_RE`). Domain's free-form strings (`"Auction"`, `"Offers over $3.3M"`, `"Price Guide $12M $12.5M"`, `"For Sale"`, `"Contact Agent"`, `"EOI"`) get a parser that yields `(kind, low, high)` tuples. Tested against handpicked Paddington fixtures.

The parser lives in a deep module, not the Domain client. Reason: it'll see reuse if/when we add REA. Keep the parser pure: input string + category, output value object, no I/O.

### `Suburb` slug strategy

Single `slug` text column per row. Because each `suburb` row carries `source`, the same locality can have two rows — one OTH, one Domain — with the slugs computed differently per vendor. No JSONB needed. Resolvers cache writes by `(source, name, postcode, state)`. A small helper `resolve_for(name, postcode, state, source)` lets callers fetch the right slug at runtime.

The reason this is preferable to one row with two slug columns: `suburb_id` is referenced from `property`, `listing`, `scrape_job`. A scraped listing always belongs to one (source, suburb) tuple; foreign-keying through a per-source suburb row keeps the relational story clean.

### Alembic migration sketch (`0006_multi_vendor.py`)

One migration. Steps:

1. `CREATE TYPE vendor AS ENUM ('oth', 'domain')`
2. `ALTER TABLE suburb ADD COLUMN source vendor NOT NULL DEFAULT 'oth'`
3. `ALTER TABLE suburb RENAME COLUMN oth_slug TO slug`
4. Drop old unique; add `UNIQUE (source, name, postcode, state)`
5. Same pattern for `property` (add `source`, rename `oth_property_id` → `external_property_id`, replace uniques)
6. Same for `listing` (`oth_listing_id` → `external_listing_id`, add `source`, partial unique on `(source, external_listing_id)`)
7. Same for `scrape_job` and `scrape_list`
8. Add `price_display`, `price_high`, `price_kind` to `listing_snapshot`; backfill `price_kind = 'price'` where `price IS NOT NULL`, else `'unknown'`
9. Drop the `DEFAULT 'oth'` on every `source` column once backfilled (defensive — forces the writer to choose)

Rollback: reverse renames, drop new columns, drop enum. Note: the rollback loses `source='domain'` rows if any have been written between forward and reverse — document this in the migration docstring.

Sanity check after migration: `SELECT count(*) FROM suburb WHERE source = 'oth'` should equal 113.

## Phased PR breakdown

Three PRs. The seams correspond to natural fault lines: (1) a pure-refactor scaffolding pass while OTH keeps running, (2) the one atomic destructive migration, (3) the Domain implementation end-to-end including the CLI/API rename. Each merges independently; OTH stays operational throughout.

### PR 1 — Vendor scaffolding (rename + abstractions + session reparameterisation)

Pure refactor. No behaviour change for OTH, no Domain code yet, no destructive schema migration. Combines what were originally three sequential PRs because they all share the same theme — "rename and abstract, keep OTH passing" — and doing them together avoids two consecutive codemod passes over every import.

- **Goal:** Rename the service tree; introduce the `Vendor` enum and the vendor abstractions; reparameterise `scrape_session` so a second vendor can plug in later. The OTH path remains exactly equivalent.
- **Scope:**
  - `git mv services/oth-scraper services/listings-scraper`. Package rename `oth_scraper` → `listings_scraper`. `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Taskfile.yml`. Env vars stay `OTH_*` for now via pydantic-settings aliases.
  - Add `src/listings_scraper/vendor.py` with `Vendor` enum.
  - Create `vendor_clients/base.py` with `VendorListing`, `SearchPage`, `VendorClient` protocol. Move `oth_client/*` to `vendor_clients/oth/*`. Adapt OTH parser to emit `VendorListing` marked `source=Vendor.OTH`.
  - Move `suburb_resolver/*` to `vendor_resolvers/oth/*` behind a `VendorSuburbResolver` protocol.
  - Update `listing_reconciler.reconcile_batch` to take `VendorListing` and dispatch upserts by `source`.
  - Extract OTH-specifics from `scrape_session/session.py` into `scrape_session/configs/oth.py`. Add `BootstrapConfig` dataclass and `AntiBotDetector` protocol. Add `ScrapeSession.page() -> camoufox.Page` (reuses the warm browser context).
  - Alembic migration `0006_add_source_columns.py`: nullable+defaulted `source` columns on `suburb`, `property`, `listing`, `scrape_job`, `scrape_list` with default `'oth'`. **No renames yet — pure additions, all existing inserts still work.**
  - Audit OTH client tests: they currently mock `httpx.AsyncClient` directly. New `VendorClient.search()` takes a `ScrapeSession`, so migrate to a fake-session fixture in the same PR.
- **Exit criteria:** existing unit + integration tests green; OTH worker boots and scrapes Paddington end-to-end under the new module path; `session smoke --source=oth` passes against live OTH.
- **Size estimate:** large diff line-count (the codemod is wide), but mechanical. Most of it is `mv` + import rewrites.

### PR 2 — Destructive migration + price normaliser

Stays alone because schema migrations should be atomic and easily revertable. Self-contained.

- **Goal:** Rename `oth_*` columns to `external_*`; add the price representation columns; introduce the `price_normaliser/` deep module. OTH still writes only what it writes today, plus `price_display`.
- **Scope:**
  - Alembic migration `0007_rename_external_ids_and_price.py`: rename `oth_property_id` → `external_property_id`, `oth_listing_id` → `external_listing_id`, `oth_slug` → `slug`; add `price_display`, `price_high`, `price_kind` to `listing_snapshot`; backfill `price_kind = 'price'` where `price IS NOT NULL`, else `'unknown'`; drop the `'oth'` defaults on `source` columns at end (forces writers to choose).
  - New `price_normaliser/` deep module with `PriceKind`, `NormalisedPrice`, `parse_oth_listing()` (existing OTH regex moves here). Parser stays pure.
  - OTH client populates `price_display` from the OTH `displayPrice` string. `listing_reconciler` upserts by `(source, external_property_id)`.
- **Exit criteria:** integration tests green; OTH worker writes both `price` and `price_display`; row counts unchanged after migration; `SELECT count(*) FROM suburb WHERE source='oth'` returns 113.
- **Risk note:** run the migration on a clone of the live DB first. It's small (9,665 rows) but a destructive rename is worth verifying.

### PR 3 — Domain end-to-end + CLI/API rename

Domain client + Akamai-aware session config + worker dispatch + live smoke + public-surface rename. Coupled by necessity — vendor dispatch isn't testable without the vendor, and the CLI/API rename touches the same surface as the new `--source` argument, so doing them separately would mean editing the same files twice.

- **Goal:** Domain works end-to-end against the live site behind a flag; both vendors driveable from a vendor-neutral CLI and API.
- **Scope:**
  - `vendor_clients/domain/{client,next_data,parser}.py` parses `__NEXT_DATA__`. `vendor_resolvers/domain/resolver.py` builds slugs from `(name, state, postcode)`. `price_normaliser.parse_domain_price()` for free-form strings. `scrape_session/configs/domain.py` with Akamai detector (status != 200, body length floor, `_abck` contains `~-1~`).
  - Fixtures under `tests/fixtures/domain/` captured from `services/domain-spike/captures/`.
  - `worker_loop.run_worker` accepts a `VendorRegistry` mapping `Vendor` → `(VendorClient, BootstrapConfig)`. `run_job` reads `job.source` and picks the client + session config. Each vendor gets its own `ScrapeSession` instance.
  - Live e2e `tests/e2e/test_live_domain.py` gated by `RUN_LIVE_DOMAIN_TESTS=1`. Existing OTH live test untouched.
  - Decision baked in here: `tags.tagText` only contributes `"Under offer"` / `"Sold"` to `status`; `"New"` / `"Updated"` are non-material noise (skipped from diff). Documented in the parser.
  - CLI entrypoint `oth` → `scraper`. `scrape_lists run` learns `--source`. API: `/v1/scrape-lists`, `/v1/suburbs/resolve?source=oth|domain`, `/v1/jobs`. Old unversioned paths (e.g. `/scrape-lists`, `/suburbs`) keep as deprecation aliases for one release alongside the new `/v1/...` canonical routes. Env vars `OTH_*` → `LS_*` with pydantic-settings aliases. README rewrite.
- **Exit criteria:** unit tests parse the captured Paddington JSON into ≥18 `VendorListing` objects with sane field coverage; price normaliser passes a fixture-based table-test (`"Auction"`, `"Contact Agent"`, `"Offers over $X"`, `"Price Guide $X $Y"`, `"For Sale"`, `"EOI"`); live smoke produces ≥1 `listing_snapshot` row with `source='domain'`; both vendors driveable from the new CLI.
- **Size estimate:** larger than PR 2, smaller than PR 1. The CLI/API rename is mostly mechanical; the Domain client + parser is the real work.

## Risks and open questions

1. **Same physical property on two vendors.** v1 creates two `property` rows. This is a known limitation: cross-vendor dedup needs a stable address normaliser plus geocode tolerance, which is a real project. Defer to v2 and document it. The risk: queries like "all listings for 12 Smith St" double-count across vendors. Mitigation: surface this in `docs/scraper-service/DOMAIN_MODEL.md` and provide a SQL view that groups by normalised address.
2. **OTHApiClient.search signature change.** Today the worker passes `httpx.AsyncClient`; the new contract is `ScrapeSession`. PR 2 changes the OTH client to call `await session.http()` internally. This breaks any test that injects a mocked `httpx.AsyncClient` directly. Audit `tests/oth_client/*` and `tests/test_worker_loop.py` in PR 2 — they likely need to switch from `pytest_httpx` to passing a fake `ScrapeSession`. The Worker test fixture already injects a `_ScrapeSessionLike` Protocol, so worker-loop tests should be fine.
3. **Price diff churn.** Domain's `tags.tagText` (`New`, `Updated`, `Under offer`) flips often; if it lands in the diff allow-list, every scrape will produce snapshots. Decision needed before PR 5: do we treat `tags.tagText` as part of `status` (snapshot-worthy) or as a non-material noise field (skip)? Recommend: map `tags.tagText` → `status` only when it's `"Under offer"` or `"Sold"`. Treat `"New"`/`"Updated"` as non-material — they're age signals, not state changes.
4. **Akamai might escalate.** The spike was clean, but `_abck` can flip mid-session. The Domain anti-bot detector needs careful tuning, and PR 5's tests can't prove out the live failure modes. The first week of running PR 6 should include a daily check of `scrape_job WHERE last_error_class='anti_bot' AND source='domain'`.
5. **Soft-expiry semantics across vendors.** A property only listed on Domain shouldn't be soft-expired by an OTH-only sweep. The sweep already runs per-`(suburb_id, category)`, so vendor-scoping comes for free via the suburb's `source`. Verify in PR 4 that `listing.suburb_id` always references a same-source `suburb`.
6. **Migration time on a populated DB.** 9,665 properties + 9,693 snapshots is small; the renames + backfill should run in well under a minute. Still, run the migration on a clone of prod before applying.

## Out of scope for this refactor

- Detail-page fetching for either vendor (Domain `description`, `schoolCatchment`, `domainSays`).
- School catchment ingestion from Domain detail pages — sits in front of the schools-overlay map roadmap; not this work.
- REA (Kasada) as a third vendor — design accommodates it (`Vendor.REA`, new `vendor_clients/rea/`), but no scaffolding lands here.
- Cross-vendor same-physical-property dedup.
- Cron scheduling of scrape lists (`scrape_list.cron_schedule` stays reserved).
- Per-vendor proxy pools / IP rotation.
- A shared package (`packages/scraper-core`) — both vendors live in one service for now; extract later if a second service ever appears.
