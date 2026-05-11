"""Integration tests for slice 05 — narrowed runs + retry-failed.

Covers:
  - RunProducer.create_run with narrowing (suburb_ids, categories)
  - RunProducer.retry_failed
  - POST /scrape-lists/{id}/run with narrowing body
  - POST /scrape-runs/{id}/retry-failed
  - Error paths: unknown suburb_ids → 422, unknown categories → 422
  - Retry of all-succeeded run → 422
  - Retry chain (retry of retry → retried_from_run_id correctly set)
"""
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from oth_scraper.api.app import app
from oth_scraper.db.engine import get_db, get_session_factory
from oth_scraper.db.models import ScrapeJob, ScrapeList, ScrapeListSuburb, ScrapeRun, Suburb
from oth_scraper.queue import JobQueue
from oth_scraper.services.run_producer import (
    PRODUCER_CATEGORIES,
    NoFailedJobsError,
    RunResult,
    ScrapeRunNotFoundError,
    create_run,
    retry_failed,
)


# ------------------------------------------------------------------ #
# helpers                                                             #
# ------------------------------------------------------------------ #


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    name: str,
    postcode: str = "4000",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state="QLD",
                oth_slug=f"{name.lower().replace(' ', '-')}-qld-{postcode}",
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_list(
    factory: async_sessionmaker[AsyncSession],
    *,
    suburb_ids: list[int],
    filters: dict | None = None,
    name: str = "test-list",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = ScrapeList(
                name=name,
                description=None,
                filters=filters or {},
                cron_schedule=None,
            )
            session.add(row)
            await session.flush()
            list_id = row.id
            for sid in suburb_ids:
                session.add(ScrapeListSuburb(scrape_list_id=list_id, suburb_id=sid))
            await session.flush()
            return list_id


def _make_queue(factory: async_sessionmaker[AsyncSession]) -> JobQueue:
    return JobQueue(
        factory,
        max_retries_transient=3,
        max_retries_antibot=1,
        max_retries_parse=0,
        reclaim_ttl_seconds=600,
    )


async def _mark_jobs_status(
    factory: async_sessionmaker[AsyncSession],
    run_id: int,
    status: str,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Set scrape_job.status for all (or first N) jobs of a run.

    ``offset`` skips the first N jobs before applying the limit, so callers
    can mark non-overlapping slices of the job set.
    """
    async with factory() as session:
        async with session.begin():
            limit_clause = f"LIMIT {limit}" if limit else ""
            offset_clause = f"OFFSET {offset}" if offset else ""
            q = f"""
                UPDATE scrape_job
                SET status = '{status}'
                WHERE id IN (
                    SELECT id FROM scrape_job
                    WHERE run_id = {run_id}
                    ORDER BY id
                    {limit_clause}
                    {offset_clause}
                )
            """
            await session.execute(text(q))


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    def _override_get_session_factory():
        return session_factory

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = _override_get_session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
# create_run narrowing — unit-level service tests                     #
# ------------------------------------------------------------------ #


async def test_single_suburb_narrow_creates_one_run_and_three_jobs(
    session_factory,
) -> None:
    """Narrow to one suburb → 1 run + 3 jobs."""
    s1 = await _seed_suburb(session_factory, "Noosa", "4567")
    s2 = await _seed_suburb(session_factory, "Maroochydore", "4558")
    list_id = await _seed_list(session_factory, suburb_ids=[s1, s2])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await create_run(
            session,
            list_id,
            queue,
            suburb_ids=[s1],
        )

    assert result.count == 3
    assert len(result.job_ids) == 3

    async with session_factory() as session:
        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == result.run_id)
            )
        ).scalars().all()
        assert len(jobs) == 3
        assert all(j.suburb_id == s1 for j in jobs)
        assert {j.category for j in jobs} == set(PRODUCER_CATEGORIES)


async def test_single_category_narrow_creates_one_run_and_n_jobs(
    session_factory,
) -> None:
    """Narrow to one category → 1 run + N suburb jobs (one per suburb)."""
    sub_ids = [
        await _seed_suburb(session_factory, f"Sub{i}", f"450{i}")
        for i in range(4)
    ]
    list_id = await _seed_list(session_factory, suburb_ids=sub_ids)
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await create_run(
            session,
            list_id,
            queue,
            categories=["forsale"],
        )

    assert result.count == 4  # one per suburb

    async with session_factory() as session:
        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == result.run_id)
            )
        ).scalars().all()
        assert len(jobs) == 4
        assert all(j.category == "forsale" for j in jobs)


async def test_both_narrow_creates_one_run_and_one_job(
    session_factory,
) -> None:
    """Narrow to one suburb + one category → 1 run + 1 job."""
    s1 = await _seed_suburb(session_factory, "Eumundi", "4562")
    s2 = await _seed_suburb(session_factory, "Cooroy", "4563")
    list_id = await _seed_list(session_factory, suburb_ids=[s1, s2])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await create_run(
            session,
            list_id,
            queue,
            suburb_ids=[s1],
            categories=["recentlysold"],
        )

    assert result.count == 1

    async with session_factory() as session:
        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == result.run_id)
            )
        ).scalars().all()
        assert len(jobs) == 1
        assert jobs[0].suburb_id == s1
        assert jobs[0].category == "recentlysold"


async def test_full_fanout_unchanged(session_factory) -> None:
    """Omitting suburb_ids and categories → full fanout (preserve existing behaviour)."""
    sub_ids = [
        await _seed_suburb(session_factory, f"All{i}", f"460{i}")
        for i in range(3)
    ]
    list_id = await _seed_list(session_factory, suburb_ids=sub_ids)
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await create_run(session, list_id, queue)

    assert result.count == 9  # 3 suburbs × 3 categories


async def test_unknown_suburb_id_raises_value_error(session_factory) -> None:
    """suburb_ids not in the list raises ValueError."""
    s1 = await _seed_suburb(session_factory, "Known", "4001")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        try:
            await create_run(
                session,
                list_id,
                queue,
                suburb_ids=[s1, 99999],  # 99999 not in list
            )
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "99999" in str(e)


async def test_unknown_category_raises_value_error(session_factory) -> None:
    """Unknown category value raises ValueError."""
    s1 = await _seed_suburb(session_factory, "CatTest", "4002")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        try:
            await create_run(
                session,
                list_id,
                queue,
                categories=["forsale", "boguscategory"],
            )
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "boguscategory" in str(e)


# ------------------------------------------------------------------ #
# retry_failed — service-level tests                                  #
# ------------------------------------------------------------------ #


async def test_retry_failed_creates_new_run_with_failed_jobs(
    session_factory,
) -> None:
    """retry_failed copies failed/deadletter jobs into a new run."""
    s1 = await _seed_suburb(session_factory, "Buderim", "4556")
    s2 = await _seed_suburb(session_factory, "Mooloolaba", "4557")
    list_id = await _seed_list(session_factory, suburb_ids=[s1, s2])
    queue = _make_queue(session_factory)

    # Create original run (6 jobs: 2 suburbs × 3 categories).
    async with session_factory() as session:
        orig = await create_run(session, list_id, queue)

    assert orig.count == 6

    # Mark 2 jobs as failed (jobs 0,1), 1 as deadletter (job 2), 3 remain queued.
    await _mark_jobs_status(session_factory, orig.run_id, "failed", limit=2)
    await _mark_jobs_status(
        session_factory, orig.run_id, "deadletter", limit=1, offset=2
    )
    # The remaining 3 are still queued — we only retry failed/deadletter.

    async with session_factory() as session:
        retry_result = await retry_failed(session, orig.run_id, queue)

    # New run created with 3 retryable jobs (2 failed + 1 deadletter).
    assert retry_result.count == 3
    assert retry_result.run_id != orig.run_id

    async with session_factory() as session:
        new_run = await session.get(ScrapeRun, retry_result.run_id)
        assert new_run is not None
        assert new_run.trigger_source == "retry"
        assert new_run.retried_from_run_id == orig.run_id
        assert new_run.scrape_list_id == list_id

        # Original run is unmutated.
        orig_run = await session.get(ScrapeRun, orig.run_id)
        assert orig_run is not None
        assert orig_run.retried_from_run_id is None

        # New jobs are queued.
        new_jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == retry_result.run_id)
            )
        ).scalars().all()
        assert len(new_jobs) == 3
        assert all(j.status == "queued" for j in new_jobs)
        assert all(j.run_id == retry_result.run_id for j in new_jobs)


async def test_retry_all_succeeded_raises_no_failed_jobs_error(
    session_factory,
) -> None:
    """retry_failed raises NoFailedJobsError when all jobs succeeded."""
    s1 = await _seed_suburb(session_factory, "Kawana", "4575")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        orig = await create_run(session, list_id, queue)

    await _mark_jobs_status(session_factory, orig.run_id, "succeeded")

    async with session_factory() as session:
        try:
            await retry_failed(session, orig.run_id, queue)
            assert False, "Expected NoFailedJobsError"
        except NoFailedJobsError:
            pass  # correct


async def test_retry_unknown_run_raises_not_found_error(session_factory) -> None:
    """retry_failed raises ScrapeRunNotFoundError for a missing run_id."""
    queue = _make_queue(session_factory)
    async with session_factory() as session:
        try:
            await retry_failed(session, 99999999, queue)
            assert False, "Expected ScrapeRunNotFoundError"
        except ScrapeRunNotFoundError:
            pass  # correct


async def test_retry_chain_both_parents_linked(session_factory) -> None:
    """Retry of a retry → grandparent and parent both correctly linked."""
    s1 = await _seed_suburb(session_factory, "Sippy Downs", "4556")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])
    queue = _make_queue(session_factory)

    # Original run → mark 1 job failed.
    async with session_factory() as session:
        orig = await create_run(session, list_id, queue)

    await _mark_jobs_status(session_factory, orig.run_id, "failed", limit=1)

    # First retry.
    async with session_factory() as session:
        retry1 = await retry_failed(session, orig.run_id, queue)

    # Mark the retry's job failed too.
    await _mark_jobs_status(session_factory, retry1.run_id, "failed", limit=1)

    # Second retry.
    async with session_factory() as session:
        retry2 = await retry_failed(session, retry1.run_id, queue)

    async with session_factory() as session:
        r1 = await session.get(ScrapeRun, retry1.run_id)
        r2 = await session.get(ScrapeRun, retry2.run_id)
        assert r1 is not None
        assert r2 is not None
        assert r1.retried_from_run_id == orig.run_id
        assert r2.retried_from_run_id == retry1.run_id


# ------------------------------------------------------------------ #
# API endpoint tests                                                  #
# ------------------------------------------------------------------ #


async def test_api_narrow_suburb_ids(api_client, session_factory) -> None:
    """POST /scrape-lists/{id}/run with suburb_ids narrows the fanout."""
    s1 = await _seed_suburb(session_factory, "Wurtulla", "4575")
    s2 = await _seed_suburb(session_factory, "Bokarina", "4575")
    list_id = await _seed_list(session_factory, suburb_ids=[s1, s2])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"suburb_ids": [s1]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 3  # 1 suburb × 3 categories

    # Verify only s1 jobs were created.
    jobs_r = await api_client.get(f"/jobs?list_id={list_id}")
    jobs = jobs_r.json()
    assert all(j["suburb_id"] == s1 for j in jobs)


async def test_api_narrow_categories(api_client, session_factory) -> None:
    """POST /scrape-lists/{id}/run with categories narrows the fanout."""
    s1 = await _seed_suburb(session_factory, "Aroona", "4551")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"categories": ["forsale", "forrent"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2

    jobs_r = await api_client.get(f"/jobs?list_id={list_id}")
    cats = {j["category"] for j in jobs_r.json()}
    assert cats == {"forsale", "forrent"}


async def test_api_narrow_both(api_client, session_factory) -> None:
    """POST /scrape-lists/{id}/run with both suburb_ids and categories → 1 job."""
    s1 = await _seed_suburb(session_factory, "Dicky Beach", "4551")
    s2 = await _seed_suburb(session_factory, "Caloundra", "4551")
    list_id = await _seed_list(session_factory, suburb_ids=[s1, s2])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"suburb_ids": [s1], "categories": ["recentlysold"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1


async def test_api_unknown_suburb_id_returns_422(api_client, session_factory) -> None:
    """suburb_ids not in the list → 422."""
    s1 = await _seed_suburb(session_factory, "Pelican Waters", "4551")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"suburb_ids": [s1, 99999]},
    )
    assert r.status_code == 422, r.text
    assert "99999" in r.text


async def test_api_unknown_category_returns_422(api_client, session_factory) -> None:
    """Unknown categories value → 422 (Pydantic rejects it at the body level)."""
    s1 = await _seed_suburb(session_factory, "Golden Beach", "4551")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"categories": ["forsale", "notacategory"]},
    )
    assert r.status_code == 422, r.text


async def test_api_full_fanout_unchanged(api_client, session_factory) -> None:
    """Omitting narrowing body preserves the existing full-fanout behaviour."""
    sub_ids = [
        await _seed_suburb(session_factory, f"FF{i}", f"470{i}")
        for i in range(2)
    ]
    list_id = await _seed_list(session_factory, suburb_ids=sub_ids)

    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 6  # 2 suburbs × 3 categories


async def test_api_retry_failed_endpoint_happy_path(
    api_client, session_factory
) -> None:
    """POST /scrape-runs/{id}/retry-failed returns new run + job ids."""
    s1 = await _seed_suburb(session_factory, "Minyama", "4575")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])

    # Create a run (3 jobs) and mark 2 as failed.
    run_r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert run_r.status_code == 200
    orig_run_id = run_r.json()["run_id"]

    await _mark_jobs_status(session_factory, orig_run_id, "failed", limit=2)

    r = await api_client.post(f"/scrape-runs/{orig_run_id}/retry-failed")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] != orig_run_id
    assert body["count"] == 2
    assert len(body["job_ids"]) == 2

    # Verify via GET /scrape-runs.
    detail_r = await api_client.get(f"/scrape-runs/{body['run_id']}")
    assert detail_r.status_code == 200
    detail = detail_r.json()
    assert detail["trigger_source"] == "retry"
    assert detail["retried_from_run_id"] == orig_run_id


async def test_api_retry_failed_no_failed_jobs_returns_422(
    api_client, session_factory
) -> None:
    """POST /scrape-runs/{id}/retry-failed with no failed jobs → 422."""
    s1 = await _seed_suburb(session_factory, "Moffat Beach", "4551")
    list_id = await _seed_list(session_factory, suburb_ids=[s1])

    run_r = await api_client.post(f"/scrape-lists/{list_id}/run")
    orig_run_id = run_r.json()["run_id"]

    # Mark all succeeded.
    await _mark_jobs_status(session_factory, orig_run_id, "succeeded")

    r = await api_client.post(f"/scrape-runs/{orig_run_id}/retry-failed")
    assert r.status_code == 422, r.text


async def test_api_retry_failed_unknown_run_returns_404(api_client) -> None:
    """POST /scrape-runs/99999/retry-failed → 404."""
    r = await api_client.post("/scrape-runs/99999999/retry-failed")
    assert r.status_code == 404, r.text
