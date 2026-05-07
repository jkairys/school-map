# 09 — Soft-expiry sweep wired into reconciler completion

## What to build

After a successful reconcile run for `(suburb_id, category)`, run a sweep that closes listings we no longer see. v1 closure is "soft" — no detail-page hits, no definitive reason resolution.

```sql
UPDATE listing
SET closed_at = NOW(), closure_reason = 'unknown'
WHERE suburb_id = :suburb_id
  AND category = :category
  AND closed_at IS NULL
  AND last_seen_at < (NOW() - :soft_expiry_window);
```

`soft_expiry_window` is configurable via env (default: enough to cover ~3 missed scrapes — pick a sensible default like 14 days, but make the behaviour observable so users can tune it).

The sweep runs at the **end of a successful job**, after the last page has been reconciled. A failed job does NOT trigger a sweep (we don't want anti-bot hiccups falsely closing every listing in a suburb).

Add an admin REST endpoint `POST /maintenance/run-soft-expiry?suburb_id=&category=` so the sweep can be triggered manually for testing/recovery.

## Acceptance criteria

- [ ] `soft_expiry_window` is read from env; documented default in README.
- [ ] Sweep only touches listings whose `(suburb_id, category)` match the just-completed job.
- [ ] Sweep closes listings whose `last_seen_at` is older than the window with `closure_reason='unknown'`.
- [ ] Sweep does not touch listings within the window.
- [ ] Sweep does not run on a failed job — integration test asserts this.
- [ ] Manual maintenance endpoint exists and is callable.
- [ ] Integration test: seed two listings, observe one in a fresh batch, advance time past the window, run sweep — the unobserved one closes.

## Blocked by

- 08 — Property/Listing/Snapshot schema and the reconciler
