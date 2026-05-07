# 11 — Worker loop with tiered retry and dead-letter

## What to build

The consumer process. Long-running async loop:

```
while True:
    job = await queue.claim_next()
    if job is None:
        await asyncio.sleep(POLL_INTERVAL_S)
        continue
    try:
        await run_job(job)
        await queue.complete(job.id)
    except TransientError as e:
        await queue.fail(job.id, ErrorClass.transient, str(e))
    except AntiBotError as e:
        await session.rotate()
        await queue.fail(job.id, ErrorClass.anti_bot, str(e))
    except ParseError as e:
        await queue.fail(job.id, ErrorClass.parse, str(e))   # immediate dead-letter
```

`run_job(job)`:

1. Load filters from job row (already snapshotted at enqueue time).
2. Acquire the shared `ScrapeSession` (lazy bootstrap).
3. Loop pages via `OTHApiClient.search()` until no more results.
4. For each page, call `reconcile_batch(...)` from issue 08.
5. After the last page, run the soft-expiry sweep (issue 09).

Worker concurrency is configurable via env `WORKER_CONCURRENCY=3` — N async tasks share the same `ScrapeSession`, the same `RateLimiter`, and compete for jobs via `claim_next()`.

Tiered retry limits are enforced inside the queue module (issue 04): transient ≤ 3, anti-bot ≤ 1, parse = 0. Dead-lettered jobs preserve their last error class and message.

## Acceptance criteria

- [ ] Worker container, when started with N queued jobs, drains them all and exits cleanly when sent SIGTERM.
- [ ] `WORKER_CONCURRENCY=3` runs three concurrent claimers; integration test confirms 3 jobs progress in parallel against a stubbed reconciler.
- [ ] Transient error path: 5xx response from OTH client → job goes back to queue, re-runs, succeeds on second attempt → `succeeded`.
- [ ] Anti-bot path: `AntiBotError` → session rotated → job retried once → if it fails again → dead-letter.
- [ ] Parse error path: forced `ParseError` → job moves immediately to dead-letter, attempts=1.
- [ ] Soft-expiry sweep is invoked exactly once per successful job, not on failure.
- [ ] Workers do not interfere with each other when claiming jobs (covered by queue tests but reasserted here in worker-level integration test).

## Blocked by

- 04 — Postgres-backed job queue
- 08 — Property/Listing/Snapshot schema and the reconciler
- 10 — Camoufox scrape session with httpx integration and rotation policy
