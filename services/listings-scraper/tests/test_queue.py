"""Integration tests for the Postgres-backed job queue.

These tests run against a real Postgres in a testcontainer (see conftest).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.queue import (
    ErrorClass,
    Job,
    JobQueue,
    JobStatus,
    NewJob,
)


def _make_queue(
    factory: async_sessionmaker[AsyncSession], **overrides
) -> JobQueue:
    defaults = dict(
        max_retries_transient=3,
        max_retries_antibot=1,
        max_retries_parse=0,
        reclaim_ttl_seconds=600,
    )
    defaults.update(overrides)
    return JobQueue(factory, **defaults)


def _new_job(suburb_id: int = 1, category: str = "forsale") -> NewJob:
    return NewJob(
        suburb_id=suburb_id,
        category=category,
        filters={"beds_min": 3},
        scrape_list_id=None,
    )


async def test_enqueue_returns_persisted_job(session_factory):
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())

    assert isinstance(job, Job)
    assert job.id > 0
    assert job.status is JobStatus.QUEUED
    assert job.attempts == 0
    assert job.category == "forsale"
    assert job.filters == {"beds_min": 3}
    assert job.created_at is not None


async def test_claim_next_returns_none_when_empty(session_factory):
    queue = _make_queue(session_factory)
    assert await queue.claim_next() is None


async def test_claim_next_transitions_to_running(session_factory):
    queue = _make_queue(session_factory)
    enq = await queue.enqueue(_new_job())

    claimed = await queue.claim_next()

    assert claimed is not None
    assert claimed.id == enq.id
    assert claimed.status is JobStatus.RUNNING
    assert claimed.claimed_at is not None


async def test_concurrent_claim_next_each_job_claimed_exactly_once(
    session_factory,
):
    """Acceptance criterion: 10 concurrent claim_next() against 5 queued jobs.

    Each job must be claimed exactly once; 5 callers receive None.
    """
    queue = _make_queue(session_factory)
    enqueued_ids: set[int] = set()
    for i in range(5):
        job = await queue.enqueue(_new_job(suburb_id=i + 1))
        enqueued_ids.add(job.id)

    # Fire 10 concurrent claim_next() calls.
    results = await asyncio.gather(
        *(queue.claim_next() for _ in range(10))
    )

    claimed = [r for r in results if r is not None]
    nones = [r for r in results if r is None]
    assert len(claimed) == 5, "expected exactly 5 successful claims"
    assert len(nones) == 5, "expected exactly 5 callers to see None"
    assert {j.id for j in claimed} == enqueued_ids, "every job claimed exactly once"
    assert all(j.status is JobStatus.RUNNING for j in claimed)


async def test_complete_marks_succeeded(session_factory):
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())
    claimed = await queue.claim_next()
    assert claimed is not None

    await queue.complete(claimed.id)

    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, completed_at FROM scrape_job WHERE id = :id"
                ),
                {"id": job.id},
            )
        ).one()
        assert row.status == "succeeded"
        assert row.completed_at is not None


async def test_complete_is_idempotent(session_factory):
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())
    await queue.claim_next()

    await queue.complete(job.id)
    # Second call must not raise and must not error on a job already succeeded.
    await queue.complete(job.id)

    async with session_factory() as session:
        status = (
            await session.execute(
                text("SELECT status FROM scrape_job WHERE id = :id"),
                {"id": job.id},
            )
        ).scalar_one()
        assert status == "succeeded"


async def test_fail_parse_dead_letters_immediately(session_factory):
    """parse: max_retries=0 → first failure dead-letters."""
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())
    await queue.claim_next()

    failed = await queue.fail(job.id, ErrorClass.PARSE, "bad json")

    assert failed.status is JobStatus.DEADLETTER
    assert failed.attempts == 1
    assert failed.last_error_class == "parse"
    assert failed.last_error_message == "bad json"
    assert failed.completed_at is not None


async def test_fail_antibot_requeues_then_dead_letters(session_factory):
    """antibot: max_retries=1 → first failure requeues, second dead-letters."""
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())
    await queue.claim_next()

    first = await queue.fail(job.id, ErrorClass.ANTIBOT, "403")
    assert first.status is JobStatus.QUEUED
    assert first.attempts == 1
    assert first.claimed_at is None

    # The job must be re-claimable.
    reclaimed = await queue.claim_next()
    assert reclaimed is not None and reclaimed.id == job.id

    second = await queue.fail(job.id, ErrorClass.ANTIBOT, "403 again")
    assert second.status is JobStatus.DEADLETTER
    assert second.attempts == 2


async def test_fail_transient_requeues_up_to_three_then_dead_letters(
    session_factory,
):
    """transient: max_retries=3 → 3 requeues, 4th call dead-letters."""
    queue = _make_queue(session_factory)
    job = await queue.enqueue(_new_job())
    await queue.claim_next()

    for attempt in range(1, 4):
        result = await queue.fail(job.id, ErrorClass.TRANSIENT, f"5xx #{attempt}")
        assert result.status is JobStatus.QUEUED, (
            f"attempt {attempt} should requeue"
        )
        assert result.attempts == attempt
        # Re-claim so the next fail is for a running job.
        reclaimed = await queue.claim_next()
        assert reclaimed is not None and reclaimed.id == job.id

    final = await queue.fail(job.id, ErrorClass.TRANSIENT, "5xx final")
    assert final.status is JobStatus.DEADLETTER
    assert final.attempts == 4


async def test_stale_running_job_is_reclaimable(session_factory):
    """A `running` job whose claimed_at is older than the TTL is re-claimable."""
    queue = _make_queue(session_factory, reclaim_ttl_seconds=60)
    job = await queue.enqueue(_new_job())

    first_claim = await queue.claim_next()
    assert first_claim is not None
    assert first_claim.status is JobStatus.RUNNING

    # No queued jobs left and the running job's claim is fresh — nothing to do.
    assert await queue.claim_next() is None

    # Backdate claimed_at past the TTL; it's now reclaimable.
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=120)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE scrape_job SET claimed_at = :ts WHERE id = :id"
                ),
                {"ts": stale_ts, "id": job.id},
            )

    reclaimed = await queue.claim_next()
    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.status is JobStatus.RUNNING
    # claimed_at should have been bumped to ~now by the reclaim.
    assert reclaimed.claimed_at is not None
    assert reclaimed.claimed_at > stale_ts + timedelta(seconds=30)


async def test_unknown_job_id_raises(session_factory):
    queue = _make_queue(session_factory)
    with pytest.raises(LookupError):
        await queue.complete(99999)
    with pytest.raises(LookupError):
        await queue.fail(99999, ErrorClass.TRANSIENT, "x")
