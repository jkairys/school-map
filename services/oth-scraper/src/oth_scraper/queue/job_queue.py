"""JobQueue — a deep module wrapping the scrape_job table.

claim_next() uses a single ``UPDATE ... FROM (SELECT ... FOR UPDATE SKIP LOCKED) ... RETURNING``
CTE so the queued→running transition is atomic and immune to thundering-herd
double-claims. The same query also picks up ``running`` jobs whose
``claimed_at`` is older than the configured reclaim TTL.

Every terminal transition (complete, fail→deadletter) calls
``ScrapeRunFinalizer.recompute(run_id)`` after committing the job state write,
so the parent run's status is kept consistent.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.config import settings
from oth_scraper.db.models.scrape_job import ScrapeJob
from oth_scraper.queue.types import (
    ErrorClass,
    Job,
    JobStatus,
    NewJob,
    UnknownJobError,
)

logger = logging.getLogger(__name__)


_CLAIM_NEXT_SQL = text(
    """
    WITH next_job AS (
        SELECT id
        FROM scrape_job
        WHERE status = 'queued'
           OR (
                status = 'running'
                AND claimed_at IS NOT NULL
                AND claimed_at < NOW() - make_interval(secs => :reclaim_ttl_seconds)
           )
        ORDER BY
            CASE WHEN status = 'queued' THEN 0 ELSE 1 END,
            COALESCE(claimed_at, created_at)
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    UPDATE scrape_job sj
    SET status = 'running',
        claimed_at = NOW()
    FROM next_job
    WHERE sj.id = next_job.id
    RETURNING sj.id
    """
)


class JobQueue:
    """Postgres-backed queue with SKIP LOCKED claim semantics.

    Construct with an ``async_sessionmaker`` so tests can inject a sessionmaker
    bound to a throwaway test container.

    If a ``ScrapeRunFinalizer`` is injected (via ``finalizer=``), every
    terminal job transition calls ``finalizer.recompute(run_id)`` after the
    state write commits.  The finalizer is optional so existing unit tests that
    construct ``JobQueue`` without one continue to work without modification.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        reclaim_ttl_seconds: int | None = None,
        max_retries_transient: int | None = None,
        max_retries_antibot: int | None = None,
        max_retries_parse: int | None = None,
        finalizer=None,
    ) -> None:
        self._session_factory = session_factory
        self._reclaim_ttl_seconds = (
            reclaim_ttl_seconds
            if reclaim_ttl_seconds is not None
            else settings.queue_reclaim_ttl_seconds
        )
        self._max_retries = {
            ErrorClass.TRANSIENT: (
                max_retries_transient
                if max_retries_transient is not None
                else settings.queue_retry_max_transient
            ),
            ErrorClass.ANTIBOT: (
                max_retries_antibot
                if max_retries_antibot is not None
                else settings.queue_retry_max_antibot
            ),
            ErrorClass.PARSE: (
                max_retries_parse
                if max_retries_parse is not None
                else settings.queue_retry_max_parse
            ),
        }
        self._finalizer = finalizer

    async def enqueue(self, job: NewJob) -> Job:
        """Insert a job in `queued` status and return the persisted row."""
        async with self._session_factory() as session:
            async with session.begin():
                row = ScrapeJob(
                    run_id=job.run_id,
                    scrape_list_id=job.scrape_list_id,
                    suburb_id=job.suburb_id,
                    category=job.category,
                    filters=dict(job.filters),
                    status="queued",
                    attempts=0,
                )
                session.add(row)
                await session.flush()
                return _to_job(row)

    async def claim_next(self) -> Job | None:
        """Atomically transition a queued (or stale running) job to running.

        Returns the claimed Job, or None if no claimable job exists. Safe to
        call concurrently — each row is claimed by exactly one caller thanks
        to ``SELECT ... FOR UPDATE SKIP LOCKED``.

        When a stale running job is reclaimed its parent run's status is
        flipped back to ``running`` via the finalizer (if configured).
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    _CLAIM_NEXT_SQL,
                    {"reclaim_ttl_seconds": self._reclaim_ttl_seconds},
                )
                row = result.first()
                if row is None:
                    return None
                job_id = row.id
                fetched = (
                    await session.execute(
                        select(ScrapeJob).where(ScrapeJob.id == job_id)
                    )
                ).scalar_one()
                job = _to_job(fetched)

        # If this was a reclaim of a previously-terminal run, recompute so the
        # run flips back to 'running'.
        if self._finalizer is not None:
            await self._finalizer.recompute(job.run_id)

        return job

    async def complete(self, job_id: int) -> None:
        """Mark a job succeeded. Idempotent — a second call is a no-op."""
        run_id: int | None = None
        async with self._session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(ScrapeJob)
                        .where(ScrapeJob.id == job_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if row is None:
                    raise UnknownJobError(f"job {job_id} not found")
                if row.status == "succeeded":
                    return
                run_id = row.run_id
                row.status = "succeeded"
                row.completed_at = datetime.now(timezone.utc)

        if self._finalizer is not None and run_id is not None:
            await self._finalizer.recompute(run_id)

    async def fail(
        self, job_id: int, error_class: ErrorClass, message: str
    ) -> Job:
        """Record a failure for a job and either re-queue or dead-letter it.

        Increments ``attempts``; transitions to ``deadletter`` when
        ``attempts`` exceeds the per-class retry limit, otherwise back to
        ``queued`` so a later ``claim_next()`` will pick it up again.

        Calls the finalizer only when the job goes terminal (deadletter).
        """
        max_retries = self._max_retries[error_class]
        terminal = False
        run_id: int | None = None
        async with self._session_factory() as session:
            async with session.begin():
                row = (
                    await session.execute(
                        select(ScrapeJob)
                        .where(ScrapeJob.id == job_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
                if row is None:
                    raise UnknownJobError(f"job {job_id} not found")
                run_id = row.run_id
                row.attempts += 1
                row.last_error_class = error_class.value
                row.last_error_message = message
                row.claimed_at = None
                if row.attempts > max_retries:
                    row.status = "deadletter"
                    row.completed_at = datetime.now(timezone.utc)
                    terminal = True
                    logger.info(
                        "job %s dead-lettered after %d attempts (%s)",
                        job_id,
                        row.attempts,
                        error_class.value,
                    )
                else:
                    row.status = "queued"
                    logger.info(
                        "job %s requeued (attempt %d/%d, %s)",
                        job_id,
                        row.attempts,
                        max_retries,
                        error_class.value,
                    )
                await session.flush()
                result = _to_job(row)

        # Only invoke the finalizer when the job is terminal (deadletter).
        # A re-queued job is not terminal — it will be processed again.
        if terminal and self._finalizer is not None and run_id is not None:
            await self._finalizer.recompute(run_id)

        return result


def _to_job(row: ScrapeJob) -> Job:
    return Job(
        id=row.id,
        run_id=row.run_id,
        scrape_list_id=row.scrape_list_id,
        suburb_id=row.suburb_id,
        category=row.category,
        filters=dict(row.filters or {}),
        status=JobStatus(row.status),
        attempts=row.attempts,
        last_error_class=row.last_error_class,
        last_error_message=row.last_error_message,
        claimed_at=row.claimed_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )
