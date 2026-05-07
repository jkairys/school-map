"""Postgres-backed job queue for the OTH scraper service.

Public interface:
    - JobQueue.enqueue(job: NewJob) -> Job
    - JobQueue.claim_next() -> Job | None
    - JobQueue.complete(job_id: int) -> None
    - JobQueue.fail(job_id: int, error_class: ErrorClass, message: str) -> Job

Claim semantics use ``SELECT ... FOR UPDATE SKIP LOCKED`` against the
``scrape_job`` table; the same query also picks up ``running`` jobs whose
``claimed_at`` is older than the reclaim TTL.

Retry policy is enforced inside ``fail()`` based on per-class limits read
from the following environment variables (all prefixed ``OTH_``):

    - ``OTH_QUEUE_RETRY_MAX_TRANSIENT``  (default 3)
    - ``OTH_QUEUE_RETRY_MAX_ANTIBOT``    (default 1)
    - ``OTH_QUEUE_RETRY_MAX_PARSE``      (default 0)
    - ``OTH_QUEUE_RECLAIM_TTL_SECONDS``  (default 600)

The semantics of ``MAX_*`` is "max retries". After ``fail()`` increments
``attempts`` the job dead-letters when ``attempts > max_retries`` for the
given error class — so ``MAX_PARSE=0`` dead-letters on the first failure.
"""
from oth_scraper.queue.job_queue import JobQueue
from oth_scraper.queue.types import (
    ErrorClass,
    Job,
    JobStatus,
    NewJob,
    UnknownJobError,
)

__all__ = [
    "ErrorClass",
    "Job",
    "JobQueue",
    "JobStatus",
    "NewJob",
    "UnknownJobError",
]
