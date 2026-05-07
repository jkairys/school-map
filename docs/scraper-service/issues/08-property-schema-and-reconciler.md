# 08 — Property/Listing/Snapshot schema and the reconciler

## What to build

The heart of the data model: turn one batch of `OTHListing` results into the right upserts and snapshot rows. Two pieces ship together:

**Schema** (Alembic migration adds `property`, `listing`, `listing_snapshot` per the PRD):

- `property` — `oth_property_id` UNIQUE NULLABLE, secondary unique on `(formatted_address, postcode)`, `location geography(Point, 4326)` NULLABLE.
- `listing` — `(property_id, suburb_id, category)`; `first_seen_at`, `last_seen_at`, `closed_at`, `closure_reason`, `agent_name`, `agency_name`, `oth_listing_id` NULLABLE.
- `listing_snapshot` — `(listing_id, observed_at)`; full field set; `raw_payload` JSONB; `changed_fields` text[].

**Reconciler** — for one (suburb, category, batch_of_OTHListing):

```
async def reconcile_batch(suburb_id, category, listings: list[OTHListing], raw_payloads: list[dict]) -> ReconcileResult
```

For each `OTHListing`:

1. Upsert `Property` by `oth_property_id` (or fallback `(address, postcode)`).
2. Find/open a `Listing` for `(property_id, suburb_id, category)` that is not closed.
3. Load latest `ListingSnapshot` for that listing.
4. Run the diff engine.
5. If changed → insert a new `ListingSnapshot` carrying full fields + raw_payload + changed_fields list.
6. Always bump `Listing.last_seen_at = NOW()`. Always update `Listing.agent_name/agency_name` if changed (no snapshot row).

`ReconcileResult` reports counts: properties_upserted, listings_opened, snapshots_written, observations_unchanged.

The soft-expiry sweep is its own slice (issue 09) — this slice does NOT touch `closed_at`.

## Acceptance criteria

- [ ] Migration applies cleanly; PostGIS column accepts a Point.
- [ ] First reconcile of a batch produces N properties, N listings, N snapshots (initial).
- [ ] Re-reconciling the same batch produces 0 new snapshots; only `last_seen_at` bumps.
- [ ] Changing one field in a listing on re-reconcile produces exactly 1 new snapshot for that listing with `changed_fields` = `[that_field]`.
- [ ] Re-listings of the same property (same `oth_property_id`, new `oth_listing_id`) produce a second `Listing` row attached to the same `Property`.
- [ ] Agent/agency change updates the Listing row, no snapshot.
- [ ] Integration test runs against a real Postgres test container.

## Blocked by

- 05 — OTH API client (request builder + parser)
- 07 — Snapshot diff engine (pure)
