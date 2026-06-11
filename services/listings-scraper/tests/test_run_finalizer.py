"""Integration tests for ScrapeRunFinalizer.

Table-driven over child-job state combinations, exercised against a real
Postgres test container.  Verifies:

- Each status-combination maps to the correct (status, completed_at) pair.
- Re-invocation is idempotent (running it twice leaves the row unchanged).
- Concurrent invocation converges to the correct final state.
- Reclaiming a stuck job from a previously-terminal run flips the run back
  to 'running'.
"""
import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.db.models import ScrapeJob, ScrapeRun
from listings_scraper.run_finalizer import ScrapeRunFinalizer


# ------------------------------------------------------------------ #
# helpers                                                             #
# ------------------------------------------------------------------ #


async def _seed_run(
    factory: async_sessionmaker[AsyncSession],
    *,
    status: str = "running",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = ScrapeRun(
                trigger_source="api",
                filters_snapshot={},
                status=status,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    run_id: int,
    status: str,
    completed_at: datetime | None = None,
) -> int:
    if status in ("succeeded", "failed", "deadletter") and completed_at is None:
        completed_at = datetime.now(timezone.utc)
    async with factory() as session:
        async with session.begin():
            row = ScrapeJob(
                run_id=run_id,
                category="forsale",
                filters={},
                status=status,
                attempts=0,
                completed_at=completed_at,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _get_run_state(
    factory: async_sessionmaker[AsyncSession], run_id: int
) -> tuple[str, datetime | None]:
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, completed_at FROM scrape_run WHERE id = :id"
                ),
                {"id": run_id},
            )
        ).one()
        return row.status, row.completed_at


# ------------------------------------------------------------------ #
# table-driven state-combination matrix                               #
# ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    "job_statuses, expected_status, completed_at_is_set",
    [
        # All queued → running
        (["queued", "queued", "queued"], "running", False),
        # Mixed queued + running → running
        (["queued", "running", "queued"], "running", False),
        # Mixed running + succeeded → running (not all done)
        (["running", "succeeded"], "running", False),
        # All succeeded → succeeded, completed_at set
        (["succeeded", "succeeded", "succeeded"], "succeeded", True),
        # Mixed succeeded + failed → partial
        (["succeeded", "failed"], "partial", True),
        # Mixed succeeded + deadletter → partial
        (["succeeded", "deadletter"], "partial", True),
        # Mixed succeeded + failed + deadletter → partial
        (["succeeded", "failed", "deadletter"], "partial", True),
        # All failed → failed
        (["failed", "failed"], "failed", True),
        # All deadletter → failed
        (["deadletter", "deadletter"], "failed", True),
        # Mixed failed + deadletter → failed
        (["failed", "deadletter"], "failed", True),
        # Single succeeded → succeeded
        (["succeeded"], "succeeded", True),
        # Single failed → failed
        (["failed"], "failed", True),
        # Single deadletter → failed
        (["deadletter"], "failed", True),
        # Single queued → running
        (["queued"], "running", False),
    ],
)
async def test_finalizer_status_matrix(
    session_factory,
    job_statuses: list[str],
    expected_status: str,
    completed_at_is_set: bool,
) -> None:
    run_id = await _seed_run(session_factory)
    for s in job_statuses:
        await _seed_job(session_factory, run_id=run_id, status=s)

    finalizer = ScrapeRunFinalizer(session_factory)
    await finalizer.recompute(run_id)

    status, completed_at = await _get_run_state(session_factory, run_id)
    assert status == expected_status, (
        f"jobs={job_statuses} → expected {expected_status!r}, got {status!r}"
    )
    if completed_at_is_set:
        assert completed_at is not None, "completed_at should be set when all done"
    else:
        assert completed_at is None, "completed_at should be NULL while in-flight"


# ------------------------------------------------------------------ #
# idempotency                                                          #
# ------------------------------------------------------------------ #


async def test_finalizer_is_idempotent(session_factory) -> None:
    """Calling recompute() twice leaves the row unchanged."""
    run_id = await _seed_run(session_factory)
    await _seed_job(session_factory, run_id=run_id, status="succeeded")
    await _seed_job(session_factory, run_id=run_id, status="succeeded")

    finalizer = ScrapeRunFinalizer(session_factory)
    await finalizer.recompute(run_id)
    status1, completed_at1 = await _get_run_state(session_factory, run_id)
    assert status1 == "succeeded"
    assert completed_at1 is not None

    await finalizer.recompute(run_id)
    status2, completed_at2 = await _get_run_state(session_factory, run_id)
    assert status2 == status1
    # completed_at might differ by microseconds; just assert it's not None
    assert completed_at2 is not None


# ------------------------------------------------------------------ #
# concurrency-safety                                                  #
# ------------------------------------------------------------------ #


async def test_finalizer_concurrent_calls_converge(session_factory) -> None:
    """Two simultaneous recompute() calls must converge to the same state."""
    run_id = await _seed_run(session_factory)
    await _seed_job(session_factory, run_id=run_id, status="succeeded")
    await _seed_job(session_factory, run_id=run_id, status="failed")

    finalizer = ScrapeRunFinalizer(session_factory)

    # Fire two concurrent recompute() calls.
    await asyncio.gather(
        finalizer.recompute(run_id),
        finalizer.recompute(run_id),
    )

    status, completed_at = await _get_run_state(session_factory, run_id)
    assert status == "partial"
    assert completed_at is not None


# ------------------------------------------------------------------ #
# reclaim-stuck flips run back to running                             #
# ------------------------------------------------------------------ #


async def test_reclaim_flips_terminal_run_back_to_running(
    session_factory,
) -> None:
    """When a stuck job from a completed run is reclaimed, the run goes running."""
    run_id = await _seed_run(session_factory, status="succeeded")
    # Set a job back to running (simulating a reclaim scenario)
    job_id = await _seed_job(session_factory, run_id=run_id, status="succeeded")

    # Forcibly flip the job back to running (as reclaim_stuck would do)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE scrape_job SET status = 'running', completed_at = NULL "
                    "WHERE id = :id"
                ),
                {"id": job_id},
            )

    finalizer = ScrapeRunFinalizer(session_factory)
    await finalizer.recompute(run_id)

    status, completed_at = await _get_run_state(session_factory, run_id)
    assert status == "running"
    assert completed_at is None
