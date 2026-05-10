# OTH scraper — domain model

Reference for the entities the service maintains. Grounded in the actual SQLAlchemy models at `services/oth-scraper/src/oth_scraper/db/models/` (not just PRD intent — the code is the truth).

## Entity-relationship overview

```
┌──────────────────┐     ┌─────────────────────┐
│   scrape_list    │────<│ scrape_list_suburb  │>───┐
└──────────────────┘ m2m └─────────────────────┘    │
        │                                           │
        │                              ┌────────────┴───────┐
        │                              │       suburb       │
        │                              └────────┬───────────┘
        │  optional FK                          │
        │                                       │
        ↓                                       ↓
┌───────────────────┐                    ┌─────────────────┐
│   scrape_job      │ ───────────────────│   property      │
│ (queue)           │   (suburb_id)      │ (physical addr) │
└───────────────────┘                    └────────┬────────┘
                                                  │ 1
                                                  │
                                                  N
                                         ┌────────┴────────┐
                                         │    listing      │
                                         │ (campaign)      │
                                         └────────┬────────┘
                                                  │ 1
                                                  │
                                                  N
                                         ┌────────┴────────┐
                                         │ listing_snapshot│
                                         │ (insert-only)   │
                                         └─────────────────┘
```

## The big idea

- A **suburb** is a named geographic area (resolved once via OTH autocomplete, then cached).
- A **scrape list** is a user-curated set of suburbs sharing a filter set; running it fans out one **scrape job** per `(suburb × category)`.
- A **property** is a physical address. It exists once and lives forever.
- A **listing** is a marketing campaign for a property — a sale, a rental, or a recently-sold record. Same property can have many listings over time (resold, relisted, rented out then sold).
- A **listing snapshot** is a point-in-time observation of a listing's mutable state (price, blurb, particulars). Insert-only — the time-tracking data lives here.
- A **scrape job** is a queue row; the worker drives the producer-consumer pipeline.

---

## suburb

A geographic locality, name-resolved via OTH's autocomplete and cached.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | autoincrement |
| `name` | text NOT NULL | `"Mount Coolum"`, `"Maroochydore"` |
| `postcode` | text NOT NULL | `"4573"` |
| `state` | text NOT NULL | `"QLD"` |
| `oth_slug` | text NOT NULL | OTH's URL slug, e.g. `"mount-coolum"` |
| `resolved_at` | timestamptz NOT NULL | set on insert via `func.now()` |

**Constraints**: `UNIQUE (name, postcode, state)`.

**Lifecycle**: created lazily on first `POST /suburbs/resolve`. Never deleted in v1.

---

## scrape_list

A named, filtered collection of suburbs.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `name` | text NOT NULL | `"Sunshine Coast LGA"` |
| `description` | text NULLABLE | freeform |
| `filters` | jsonb NOT NULL | shape: `{beds_min, beds_max, property_types[], price_min, price_max}` |
| `cron_schedule` | text NULLABLE | reserved for v2 — v1 ignores |
| `created_at` | timestamptz NOT NULL | |

**Filter JSON shape** (validated by Pydantic on write):
```json
{
  "beds_min": 1,
  "beds_max": null,
  "property_types": ["House", "Townhouse", "Unit", "Apartment", "Land"],
  "price_min": null,
  "price_max": null
}
```

### scrape_list_suburb (m2m)

| Column | Type | Notes |
|---|---|---|
| `scrape_list_id` | bigint FK | `→ scrape_list.id ON DELETE CASCADE` |
| `suburb_id` | bigint FK | `→ suburb.id ON DELETE RESTRICT` |

Composite PK on `(scrape_list_id, suburb_id)`. Removing a suburb from a list never deletes the suburb row.

---

## scrape_job

The Postgres-backed work queue. One row per `(suburb × category)` enqueue.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `scrape_list_id` | bigint FK NULLABLE | `→ scrape_list.id`. NULL for ad-hoc jobs |
| `suburb_id` | bigint FK NULLABLE | `→ suburb.id` |
| `category` | varchar(32) NOT NULL | `forsale` / `forrent` / `recentlysold` (free-form string here, not the enum — predates the enum) |
| `filters` | jsonb NOT NULL | snapshotted from the list at enqueue — editing the list later does NOT mutate in-flight jobs |
| `status` | enum NOT NULL | `queued` / `running` / `succeeded` / `failed` / `deadletter` |
| `attempts` | int NOT NULL | incremented by `fail()` |
| `last_error_class` | varchar(32) NULLABLE | `transient` / `anti_bot` / `parse` |
| `last_error_message` | text NULLABLE | |
| `claimed_at` | timestamptz NULLABLE | set when status flips to `running` |
| `completed_at` | timestamptz NULLABLE | set when terminal (`succeeded`/`failed`/`deadletter`) |
| `created_at` | timestamptz NOT NULL | |

**Indexes**:
- `(status, created_at)` — for `claim_next()` ordering
- `(claimed_at)` — for the reclaim sweep

**State machine**:
```
                    ┌─→ succeeded
queued → running ───┤
                    └─→ failed → queued (retry)
                              └─→ deadletter (attempts exhausted OR parse error)
```

**Retry limits per error class** (env-tuned):
| Class | Default max retries | Behaviour |
|---|---|---|
| `transient` | 3 | exp backoff |
| `anti_bot` | 1 | session rotated by worker before retry |
| `parse` | 0 | immediate dead-letter (it's a code bug) |

**Reclaim**: a `running` row whose `claimed_at` is older than `OTH_QUEUE_RECLAIM_TTL_SECONDS` (default 600s) is reclaimable. Recovers from worker crashes mid-job.

---

## property

A physical address. Created once, exists forever — multiple listings attach to it over time.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `oth_property_id` | text NULLABLE | OTH's stable property identifier — UNIQUE when present |
| `formatted_address` | text NOT NULL | `"12 Smith St, Mount Coolum, QLD 4573"` |
| `postcode` | text NOT NULL | |
| `suburb_id` | bigint FK NOT NULL | `→ suburb.id ON DELETE RESTRICT` |
| `location` | `geography(POINT, 4326)` NULLABLE | PostGIS, WGS84. Often NULL for older recently-sold rows |
| `first_seen_at` | timestamptz NOT NULL | |

**Constraints**:
- `UNIQUE (oth_property_id)` — primary natural key
- `UNIQUE (formatted_address, postcode)` — fallback when `oth_property_id` is missing

**Reconciler upsert order**: try `oth_property_id` first; fall back to `(formatted_address, postcode)` if no OTH ID present.

---

## listing

A marketing campaign for a property — one of `forsale` / `forrent` / `recentlysold`.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `property_id` | bigint FK NOT NULL | `→ property.id ON DELETE CASCADE` |
| `suburb_id` | bigint FK NOT NULL | `→ suburb.id ON DELETE RESTRICT` (denormalised for query speed) |
| `category` | enum NOT NULL | `forsale` / `forrent` / `recentlysold` |
| `oth_listing_id` | text NULLABLE | |
| `agent_name` | text NULLABLE | mutable on the row (no snapshot) |
| `agency_name` | text NULLABLE | mutable on the row (no snapshot) |
| `first_seen_at` | timestamptz NOT NULL | |
| `last_seen_at` | timestamptz NOT NULL | bumped on every observation |
| `closed_at` | timestamptz NULLABLE | set by soft-expiry sweep |
| `closure_reason` | enum NULLABLE | `unknown` / `sold` / `withdrawn` / `expired`. v1 only writes `unknown` |

**Indexes**:
- **Hot reconciler lookup** — partial index on `(property_id, suburb_id, category) WHERE closed_at IS NULL`
- `(suburb_id, category)` — read-side suburb queries
- `(last_seen_at)` — soft-expiry sweep scan

**Open / closed**: a listing is "open" iff `closed_at IS NULL`. v1 closes via soft expiry only — `last_seen_at < NOW() - 14d` flips to `closed_at = NOW(), closure_reason = 'unknown'` after a successful job.

**Re-listing semantics**: a property re-listed gets a NEW listing row (new `oth_listing_id`, new `first_seen_at`) attached to the SAME `property_id`. Use this to count "how many times has 12 Smith St been listed".

---

## listing_snapshot

The time-tracking core. **Insert-only** — every row is an observation that materially differed from its predecessor.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint PK | |
| `listing_id` | bigint FK NOT NULL | `→ listing.id ON DELETE CASCADE` |
| `observed_at` | timestamptz NOT NULL | |
| `price` | int NULLABLE | sale price for `forsale`/`recentlysold`; weekly rent for `forrent` |
| `title` | text NULLABLE | |
| `blurb` | text NULLABLE | NULL in v1 — populated only when v2 visits detail pages |
| `bedrooms` | int NULLABLE | |
| `bathrooms` | int NULLABLE | |
| `parking` | int NULLABLE | |
| `land_size_sqm` | int NULLABLE | |
| `property_type` | text NULLABLE | `"House"` / `"Townhouse"` / etc. |
| `status` | text NULLABLE | OTH's status string (e.g. `"Active"`, `"UnderContract"`) |
| `raw_payload` | jsonb NOT NULL | full OTH JSON for the listing — write-once |
| `changed_fields` | text[] NOT NULL | which material fields changed vs prior snapshot. First snapshot contains `__initial__` |

**Indexes**:
- `(listing_id, observed_at)` — for snapshot history queries

**Material fields** (the diff allow-list — agent/agency NOT included):
```
price, title, blurb, bedrooms, bathrooms, parking,
land_size_sqm, property_type, status
```

Agent/agency changes update the **listing** row, never produce a snapshot.

**Invariants**:
- Insert-only — never UPDATE a snapshot. `raw_payload` is write-once.
- The first snapshot for a listing has `changed_fields` starting with `__initial__`.
- A re-observation that finds no material change writes NO snapshot — just bumps `listing.last_seen_at`.

---

## How a single observation flows

For one listing returned by an OTH search batch in a `(suburb, category)` job:

```
1. upsert property (oth_property_id, fallback address+postcode)
2. find or open listing for (property_id, suburb_id, category) where closed_at IS NULL
3. load latest listing_snapshot for this listing (or NULL)
4. snapshot_diff(prev, new):
     - prev IS NULL → ChangedFields(["__initial__", ...])
     - identical    → None
     - changed      → ChangedFields([field, ...])
5. if changed → INSERT listing_snapshot (full fields + raw_payload + changed_fields)
6. UPDATE listing SET last_seen_at = NOW(), agent_name = ?, agency_name = ?
```

After the last page of the job: soft-expiry sweep over `(suburb, category)` closes any listing with `last_seen_at < NOW() - OTH_SOFT_EXPIRY_DAYS`.

---

## Common queries

**Active for-sale listings in a suburb:**
```sql
SELECT l.*, s.* FROM listing l
JOIN listing_snapshot s ON s.listing_id = l.id
JOIN suburb sb ON sb.id = l.suburb_id
WHERE sb.name = 'Mount Coolum' AND l.category = 'forsale' AND l.closed_at IS NULL
  AND s.observed_at = (SELECT MAX(observed_at) FROM listing_snapshot WHERE listing_id = l.id);
```

**Price-change history for one listing:**
```sql
SELECT observed_at, price, changed_fields
FROM listing_snapshot
WHERE listing_id = :id
ORDER BY observed_at;
```

**What changed in the last 24h across all suburbs (excluding initial-observation noise):**
```sql
SELECT s.observed_at, p.formatted_address, l.category, s.changed_fields, s.price
FROM listing_snapshot s
JOIN listing l ON s.listing_id = l.id
JOIN property p ON l.property_id = p.id
WHERE s.observed_at > NOW() - INTERVAL '24 hours'
  AND NOT s.changed_fields @> ARRAY['__initial__']
ORDER BY s.observed_at DESC;
```

**Re-listing detection — properties with > 1 listing campaign:**
```sql
SELECT p.formatted_address, COUNT(l.id) AS campaigns,
       MIN(l.first_seen_at) AS first_listed,
       MAX(l.first_seen_at) AS last_listed
FROM listing l JOIN property p ON p.id = l.property_id
GROUP BY p.id, p.formatted_address
HAVING COUNT(l.id) > 1
ORDER BY 2 DESC;
```

**Job queue snapshot** (operational):
```sql
SELECT status, COUNT(*) FROM scrape_job GROUP BY status;
SELECT last_error_class, COUNT(*) FROM scrape_job
WHERE status='deadletter' GROUP BY 1;
```

---

## Sample dataset (post-Sunshine-Coast-LGA scrape, 2026-05-08)

Reference numbers from the first real run, useful as a sanity baseline:

| Entity | Count |
|---|---|
| suburb | 113 |
| scrape_list | 1 |
| scrape_job (all `succeeded`) | 339 |
| property | 9,665 |
| listing (all open) | 9,686 |
| listing (`recentlysold`) | 8,244 |
| listing (`forsale`) | 1,173 |
| listing (`forrent`) | 269 |
| listing_snapshot (all `__initial__`) | 9,693 |

A full re-run produces ≪ 9,693 new snapshots (only the deltas).
