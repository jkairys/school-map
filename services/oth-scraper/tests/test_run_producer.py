"""Integration tests for the run producer.

Verifies the "1 scrape_run + N scrape_jobs all linked via run_id" guarantee.
"""
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.db.models import ScrapeJob, ScrapeList, ScrapeListSuburb, ScrapeRun, Suburb
from oth_scraper.queue import JobQueue
from oth_scraper.services.scrape_list import PRODUCER_CATEGORIES, run_list


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
) -> int:
    async with factory() as session:
        async with session.begin():
            row = ScrapeList(
                name="test-list",
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


# ------------------------------------------------------------------ #
# tests                                                               #
# ------------------------------------------------------------------ #


async def test_one_suburb_run_creates_one_run_and_three_jobs(
    session_factory,
) -> None:
    """1-suburb list → 1 scrape_run + 3 scrape_jobs, all linked via run_id."""
    sub_id = await _seed_suburb(session_factory, "Noosa")
    list_id = await _seed_list(session_factory, suburb_ids=[sub_id])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await run_list(session, list_id, queue, trigger_source="api")

    assert result.count == 3
    assert result.run_id > 0
    assert len(result.job_ids) == 3

    # Verify DB state.
    async with session_factory() as session:
        run = await session.get(ScrapeRun, result.run_id)
        assert run is not None
        assert run.scrape_list_id == list_id
        assert run.trigger_source == "api"
        assert run.status == "running"

        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == result.run_id)
            )
        ).scalars().all()
        assert len(jobs) == 3
        assert all(j.run_id == result.run_id for j in jobs)
        cats = {j.category for j in jobs}
        assert cats == set(PRODUCER_CATEGORIES)


async def test_three_suburb_run_creates_one_run_and_nine_jobs(
    session_factory,
) -> None:
    """3-suburb list → 1 + 3×3 = 10 total rows, all linked via run_id."""
    sub_ids = [
        await _seed_suburb(session_factory, f"Sub{i}", f"400{i}")
        for i in range(3)
    ]
    list_id = await _seed_list(session_factory, suburb_ids=sub_ids)
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await run_list(session, list_id, queue, trigger_source="cli")

    assert result.count == 9
    assert result.run_id > 0

    async with session_factory() as session:
        # 1 scrape_run row.
        run_count = (
            await session.execute(text("SELECT count(*) FROM scrape_run"))
        ).scalar_one()
        assert run_count == 1

        # 9 scrape_job rows, all with the same run_id.
        jobs = (
            await session.execute(
                select(ScrapeJob).where(ScrapeJob.run_id == result.run_id)
            )
        ).scalars().all()
        assert len(jobs) == 9
        assert all(j.run_id == result.run_id for j in jobs)


async def test_trigger_source_cli_stored_on_run(session_factory) -> None:
    """CLI trigger_source is persisted to the run row."""
    sub_id = await _seed_suburb(session_factory, "Brisbane")
    list_id = await _seed_list(session_factory, suburb_ids=[sub_id])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await run_list(session, list_id, queue, trigger_source="cli")

    async with session_factory() as session:
        run = await session.get(ScrapeRun, result.run_id)
        assert run is not None
        assert run.trigger_source == "cli"


async def test_filters_snapshot_copied_to_run(session_factory) -> None:
    """The list's filters at enqueue time are snapshotted on the run row."""
    sub_id = await _seed_suburb(session_factory, "Gold Coast")
    list_id = await _seed_list(
        session_factory,
        suburb_ids=[sub_id],
        filters={"beds_min": 3, "beds_max": None, "property_types": ["House"],
                 "price_min": None, "price_max": 1_500_000},
    )
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await run_list(session, list_id, queue)

    async with session_factory() as session:
        run = await session.get(ScrapeRun, result.run_id)
        assert run is not None
        assert run.filters_snapshot["beds_min"] == 3
        assert run.filters_snapshot["price_max"] == 1_500_000


async def test_empty_list_creates_run_with_zero_jobs(session_factory) -> None:
    """An empty list still creates a scrape_run row with 0 child jobs."""
    list_id = await _seed_list(session_factory, suburb_ids=[])
    queue = _make_queue(session_factory)

    async with session_factory() as session:
        result = await run_list(session, list_id, queue)

    assert result.count == 0
    assert result.run_id > 0

    async with session_factory() as session:
        run = await session.get(ScrapeRun, result.run_id)
        assert run is not None
        job_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM scrape_job WHERE run_id = :rid"
                ),
                {"rid": result.run_id},
            )
        ).scalar_one()
        assert job_count == 0
