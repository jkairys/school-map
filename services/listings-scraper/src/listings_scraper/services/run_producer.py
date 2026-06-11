"""RunProducer — shared entry point for creating scrape_run + scrape_job rows.

Both the REST API and the CLI call these functions.  The queue's own session
is separate so the run row is committed before jobs are enqueued (FK safety).

Entry points
------------
create_run(session, list_id, *, suburb_ids, categories, trigger_source)
    Create one scrape_run + the appropriate scrape_job rows.
    Validation (unknown suburb_ids, unknown categories) raises ValueError with
    a descriptive message; the caller turns that into a 422.

retry_failed(session, run_id, queue)
    Copy failed/deadletter jobs from an existing run into a new run with
    trigger_source='retry' and retried_from_run_id set.
    Raises NoFailedJobsError when the parent run has no retryable jobs.
    Raises ScrapeRunNotFoundError when the parent run doesn't exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.db.models.scrape_job import ScrapeJob
from listings_scraper.db.models.scrape_list import ScrapeList, ScrapeListSuburb
from listings_scraper.db.models.scrape_run import ScrapeRun
from listings_scraper.queue import JobQueue, NewJob
from listings_scraper.vendor import Vendor

PRODUCER_CATEGORIES: tuple[str, ...] = ("forsale", "forrent", "recentlysold")
"""Ordered default category set used when no narrowing is requested."""

_RETRYABLE_STATUSES: frozenset[str] = frozenset({"failed", "deadletter"})


@dataclass
class RunResult:
    """Return value from both create_run and retry_failed."""

    run_id: int
    list_id: int | None
    job_ids: list[int]
    count: int


class ScrapeRunNotFoundError(LookupError):
    """Raised when retry_failed is called with an unknown run_id."""


class NoFailedJobsError(Exception):
    """Raised when retry_failed finds no failed/deadletter jobs in a run."""


async def create_run(
    session: AsyncSession,
    list_id: int,
    queue: JobQueue,
    *,
    suburb_ids: list[int] | None = None,
    categories: list[str] | None = None,
    trigger_source: str = "api",
    source: Vendor = Vendor.OTH,
) -> RunResult:
    """Create one scrape_run + the corresponding scrape_job rows.

    Parameters
    ----------
    session:
        AsyncSession used for the scrape_run INSERT and validation queries.
        The caller is responsible for providing a live session; this function
        commits it when the run row is persisted.
    list_id:
        Must reference an existing scrape_list row.
    queue:
        JobQueue used to enqueue the scrape_job rows (uses its own session).
    suburb_ids:
        Optional list of suburb ids to fan out for.  Must be a subset of the
        suburb ids attached to ``list_id``.  When None/empty, all suburbs in
        the list are used.
    categories:
        Optional list of category strings (``'forsale'``, ``'forrent'``,
        ``'recentlysold'``).  When None/empty, all three are used.
    trigger_source:
        Value stored on scrape_run.trigger_source.

    Raises
    ------
    LookupError:
        list_id not found.
    ValueError:
        suburb_ids contains an id not in the list, or categories contains an
        unknown value.
    """
    row = await session.get(ScrapeList, list_id)
    if row is None:
        raise LookupError(f"scrape_list {list_id} not found")

    filters_snapshot: dict[str, Any] = dict(row.filters or {})

    # Resolve the full set of suburb ids attached to the list.
    all_suburb_ids_stmt = (
        select(ScrapeListSuburb.suburb_id)
        .where(ScrapeListSuburb.scrape_list_id == list_id)
        .order_by(ScrapeListSuburb.suburb_id)
    )
    all_suburb_ids: set[int] = set(
        (await session.execute(all_suburb_ids_stmt)).scalars().all()
    )

    # Resolve narrowed suburb set.
    if suburb_ids:
        unknown = set(suburb_ids) - all_suburb_ids
        if unknown:
            raise ValueError(
                f"suburb_ids {sorted(unknown)} are not in scrape_list {list_id}"
            )
        effective_suburb_ids = [sid for sid in suburb_ids if sid in all_suburb_ids]
    else:
        effective_suburb_ids = sorted(all_suburb_ids)

    # Resolve narrowed category set.
    if categories:
        unknown_cats = set(categories) - set(PRODUCER_CATEGORIES)
        if unknown_cats:
            raise ValueError(
                f"unknown categories {sorted(unknown_cats)}; "
                f"valid values are {list(PRODUCER_CATEGORIES)}"
            )
        effective_categories = [c for c in PRODUCER_CATEGORIES if c in categories]
    else:
        effective_categories = list(PRODUCER_CATEGORIES)

    # Insert the scrape_run row first and commit so jobs can FK to it.
    run = ScrapeRun(
        scrape_list_id=list_id,
        trigger_source=trigger_source,
        filters_snapshot=filters_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    job_ids: list[int] = []
    for suburb_id in effective_suburb_ids:
        for category in effective_categories:
            job = await queue.enqueue(
                NewJob(
                    run_id=run.id,
                    suburb_id=suburb_id,
                    category=category,
                    filters=dict(filters_snapshot),
                    scrape_list_id=list_id,
                    source=source,
                )
            )
            job_ids.append(job.id)

    return RunResult(
        run_id=run.id,
        list_id=list_id,
        job_ids=job_ids,
        count=len(job_ids),
    )


async def retry_failed(
    session: AsyncSession,
    run_id: int,
    queue: JobQueue,
) -> RunResult:
    """Re-enqueue failed/deadletter jobs from an existing run as a NEW run.

    The original run is NEVER mutated.  The new run gets
    ``trigger_source='retry'`` and ``retried_from_run_id=run_id``.

    Parameters
    ----------
    session:
        AsyncSession used for queries and the new scrape_run INSERT.
    run_id:
        Id of the run whose failed/deadletter jobs should be retried.
    queue:
        JobQueue used to enqueue the new scrape_job rows.

    Raises
    ------
    ScrapeRunNotFoundError:
        run_id does not exist.
    NoFailedJobsError:
        The run has no failed or deadletter child jobs.
    """
    parent = await session.get(ScrapeRun, run_id)
    if parent is None:
        raise ScrapeRunNotFoundError(f"scrape_run {run_id} not found")

    failed_jobs_stmt = (
        select(ScrapeJob)
        .where(
            ScrapeJob.run_id == run_id,
            ScrapeJob.status.in_(list(_RETRYABLE_STATUSES)),
        )
        .order_by(ScrapeJob.id)
    )
    failed_jobs = (await session.execute(failed_jobs_stmt)).scalars().all()

    if not failed_jobs:
        raise NoFailedJobsError(
            f"run {run_id} has no failed or deadletter jobs to retry"
        )

    # Inherit the parent's filters_snapshot for the new run.
    new_run = ScrapeRun(
        scrape_list_id=parent.scrape_list_id,
        trigger_source="retry",
        filters_snapshot=dict(parent.filters_snapshot or {}),
        retried_from_run_id=run_id,
        status="running",
    )
    session.add(new_run)
    await session.commit()
    await session.refresh(new_run)

    job_ids: list[int] = []
    for old_job in failed_jobs:
        new_job = await queue.enqueue(
            NewJob(
                run_id=new_run.id,
                suburb_id=old_job.suburb_id,
                category=old_job.category,
                filters=dict(old_job.filters or {}),
                scrape_list_id=old_job.scrape_list_id,
                source=old_job.source,
            )
        )
        job_ids.append(new_job.id)

    return RunResult(
        run_id=new_run.id,
        list_id=parent.scrape_list_id,
        job_ids=job_ids,
        count=len(job_ids),
    )
