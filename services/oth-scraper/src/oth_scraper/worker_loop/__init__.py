"""Worker loop — coordination module.

Drains the `scrape_job` queue with a configurable pool of async tasks. For
each claimed job it:

1. Loads the suburb row referenced by the job into a `ResolvedSuburb`.
2. Acquires the shared `ScrapeSession`'s httpx client (lazy bootstrap).
3. Paginates `OTHApiClient.search(...)` until `has_next == False`.
4. Runs `reconcile_batch(...)` on every page.
5. Runs `run_soft_expiry_sweep(...)` once at the end of a successful job.

Errors are classified into the `ErrorClass` taxonomy and forwarded to
`JobQueue.fail(...)`; the queue applies per-class retry limits so the
worker only has to tag the failure, not decide whether to retry.

`run_worker(...)` boots the dependency graph (DB pool, RateLimiter,
ScrapeSession, JobQueue), spawns N tasks running the loop, traps SIGTERM
to drain in-flight jobs cleanly, and exits 0 when all tasks return.
"""

from oth_scraper.worker_loop.loop import (
    classify_exception,
    run_job,
    run_worker,
    worker_task,
)

__all__ = [
    "classify_exception",
    "run_job",
    "run_worker",
    "worker_task",
]
