# 03 — ScrapeList CRUD with filter validation

## What to build

A user-facing concept: a named list of suburbs with a shared filter set. Implements the `scrape_list` table, its m2m to `suburb`, the filter-validation logic, and the CRUD surface on REST + CLI.

Filter shape (JSONB on `scrape_list`):

```json
{
  "beds_min": 3,
  "beds_max": 4,
  "property_types": ["House", "Townhouse"],
  "price_min": null,
  "price_max": 1500000
}
```

A Pydantic model validates the shape on write; unknown keys are rejected; ranges where `min > max` are rejected. The `cron_schedule` column is a nullable string reserved for v2 — v1 ignores it.

Adding a suburb to a list goes through the resolver from issue 02 — if the name is ambiguous the endpoint returns 409 with candidates and the caller retries with `(name, postcode)` disambiguation.

REST surface:

- `POST /scrape-lists` — create
- `GET /scrape-lists`, `GET /scrape-lists/{id}`
- `PUT /scrape-lists/{id}` — update name, description, filters
- `POST /scrape-lists/{id}/suburbs` — add (resolves first; 409 on ambiguity)
- `DELETE /scrape-lists/{id}/suburbs/{suburb_id}` — remove
- `DELETE /scrape-lists/{id}` — delete (cascade m2m only; never delete suburb rows)

CLI mirrors: `oth list create / show / ls / update / add-suburb / rm-suburb / rm`.

## Acceptance criteria

- [ ] `scrape_list` and `scrape_list_suburb` tables created via Alembic migration.
- [ ] All REST endpoints behave as specified, validated by an httpx-against-test-app integration test per endpoint.
- [ ] Filter validation rejects unknown keys, negative numbers, and inverted ranges with a 422.
- [ ] Adding an ambiguous suburb returns 409 with candidate list.
- [ ] Removing a suburb from a list does not delete the suburb row.
- [ ] CLI commands work end-to-end against a running api container.
- [ ] `cron_schedule` column exists, accepts null, and is ignored by v1 logic.

## Blocked by

- 02 — Suburb resolver via OTH autocomplete
