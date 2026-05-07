# 14 — Live E2E smoke test gated by env flag

## What to build

A single end-to-end test that exercises the full producer-consumer path against real OTH for one small suburb. Gated behind `RUN_LIVE_OTH_TESTS=1` so it never runs in default CI; intended to be run manually before releases.

The test:

1. Boots the api + worker against a fresh Postgres test database.
2. Resolves a known small suburb (e.g. "Mount Coolum, QLD").
3. Creates a scrape list with that suburb and a permissive filter set.
4. Triggers `POST /scrape-lists/{id}/run`.
5. Waits up to a generous timeout (e.g. 5 min) for all 3 jobs to reach a terminal state.
6. Asserts that at least one Listing has been recorded with at least one Snapshot.
7. Tears down.

The test is a single pytest function. Its failure modes (anti-bot, OTH outage, suburb has zero listings) should produce useful diagnostics — print the queued/dead-lettered job counts and the last error message per dead-lettered job, so a release-time failure is debuggable.

A short README section under `services/oth-scraper/` documents:

- How to run: `RUN_LIVE_OTH_TESTS=1 uv run pytest tests/e2e/test_live_smoke.py`.
- What anti-bot failure looks like and the rotation knobs to consider.
- That this test is not run in CI and is the developer's responsibility before merging changes that touch the scrape session or API client.

## Acceptance criteria

- [ ] Test exists at `tests/e2e/test_live_smoke.py` and is skipped by default.
- [ ] With `RUN_LIVE_OTH_TESTS=1`, it executes against real OTH and passes for a known small suburb.
- [ ] Failure output prints terminal job statuses and last errors for the dead-lettered jobs.
- [ ] README section documents how and when to run it.
- [ ] CI configuration confirmed: this test does not appear in default test runs.

## Blocked by

- 12 — Producer fan-out + read API endpoints
