# 07 — Snapshot diff engine (pure)

## What to build

A pure function with one job: decide whether a new observation of a listing differs materially from the previous snapshot, and report which fields changed.

```
def diff(prev: ListingSnapshot | None, new: OTHListing) -> ChangedFields | None
```

- `prev is None` → returns `ChangedFields(["__initial__", *all_observed_fields])`.
- All material fields equal → returns `None`.
- Otherwise → returns `ChangedFields([field_name, ...])`.

Material fields (the allow-list): `price`, `title`, `blurb`, `bedrooms`, `bathrooms`, `parking`, `land_size_sqm`, `property_type`, `status`. Agent/agency changes do **not** trigger a snapshot (record them on the Listing row only, in issue 08). `last_seen_at` is bumped elsewhere unconditionally.

Normalisation rules applied before comparison:

- Strings: trimmed, internal whitespace collapsed, case preserved.
- Prices: integer AUD; weekly rent compared as integer weekly amount.
- Property type: lowercased.
- Nulls: `None == None`.

Pure module, no IO, no DB.

## Acceptance criteria

- [ ] Table-driven unit tests cover every material field's change.
- [ ] Identical observation (including whitespace-only blurb diff) returns `None`.
- [ ] Initial observation returns `ChangedFields` containing `"__initial__"`.
- [ ] Agent/agency change alone returns `None` (those are tracked on the Listing row, not in snapshots).
- [ ] Property-type case differences are not reported as changes.
- [ ] No IO performed — verified by a static check that no DB or http imports leak in.

## Blocked by

- 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic
