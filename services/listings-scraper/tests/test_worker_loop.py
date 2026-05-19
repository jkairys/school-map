"""Integration tests for the worker loop.

Run against a real Postgres testcontainer (see conftest). Each test wires
up a real `JobQueue` against a throwaway DB, plus stub `OTHApiClient` /
`ScrapeSession` objects local to the test file — the briefing forbids
production seams that exist only for tests, but stubs that satisfy the
worker's structural protocols are fair game.
"""
import asyncio
import time

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.db.models import Suburb
from listings_scraper.vendor import Vendor
from listings_scraper.oth_client import (
    Category,
    ListingFilters,
    OTHListing,
    ParseError,
    ResolvedSuburb,
    SearchPage,
)
from listings_scraper.queue import JobQueue, JobStatus, NewJob
from listings_scraper.scrape_session import AntiBotError
from listings_scraper.worker_loop import run_worker


# ---- harness --------------------------------------------------------------


def _make_queue(factory: async_sessionmaker[AsyncSession]) -> JobQueue:
    return JobQueue(
        factory,
        max_retries_transient=3,
        max_retries_antibot=1,
        max_retries_parse=0,
        reclaim_ttl_seconds=600,
    )


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    name: str = "Paddington",
    postcode: str = "4064",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state="QLD",
                slug=f"{name.lower()}-qld-{postcode}",
                source=Vendor.OTH,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _enqueue(queue: JobQueue, suburb_id: int, n: int = 1) -> list[int]:
    ids: list[int] = []
    for _ in range(n):
        job = await queue.enqueue(
            NewJob(suburb_id=suburb_id, category="forsale", filters={})
        )
        ids.append(job.id)
    return ids


async def _count_status(
    factory: async_sessionmaker[AsyncSession], status: str
) -> int:
    async with factory() as session:
        return (
            await session.execute(
                text(
                    "SELECT count(*) FROM scrape_job WHERE status = :s"
                ),
                {"s": status},
            )
        ).scalar_one()


async def _wait_until_status_count(
    factory: async_sessionmaker[AsyncSession],
    status: str,
    expected: int,
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    last = -1
    while True:
        last = await _count_status(factory, status)
        if last >= expected:
            return
        if time.monotonic() > deadline:
            raise AssertionError(
                f"timeout waiting for {expected} jobs in '{status}'; got {last}"
            )
        await asyncio.sleep(0.05)


def _empty_page() -> SearchPage:
    return SearchPage(
        listings=[], raw_payloads=[], total=0, page=0, has_next=False
    )


def _http_error(status_code: int = 503) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/")
    response = httpx.Response(status_code, request=request, text="upstream")
    return httpx.HTTPStatusError(
        f"{status_code}", request=request, response=response
    )


class StubScrapeSession:
    """Minimal `ScrapeSession`-shaped stub. `http()` returns a real
    `httpx.AsyncClient` so calls that pass it through to a (mocked) HTTP
    layer don't blow up; in these tests the stub OTH client ignores it."""

    def __init__(self) -> None:
        self.rotate_calls = 0
        self._client = httpx.AsyncClient()

    async def http(self) -> httpx.AsyncClient:
        return self._client

    async def rotate(self) -> None:
        self.rotate_calls += 1

    async def close(self) -> None:
        await self._client.aclose()


class StubOTHClient:
    """Stub satisfying `_OTHClientLike`. `behavior` is an async callable
    invoked with `(suburb, category, filters, page)`; whatever it returns
    or raises is what `search()` returns or raises."""

    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self.calls: list[tuple[ResolvedSuburb, Category, int]] = []

    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,
        filters: ListingFilters,
        page: int,
        http: httpx.AsyncClient,
    ) -> SearchPage:
        self.calls.append((suburb, category, page))
        return await self._behavior(suburb, category, filters, page)


class _SoftExpirySpy:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Category]] = []

    async def __call__(
        self, suburb_id, category, *, session_factory, soft_expiry_window=None
    ) -> int:
        self.calls.append((suburb_id, category))
        return 0


async def _start_worker(
    *,
    queue: JobQueue,
    factory: async_sessionmaker[AsyncSession],
    oth_client,
    session: StubScrapeSession,
    soft_expiry_sweep,
    concurrency: int = 1,
    poll_interval_s: float = 0.05,
):
    shutdown = asyncio.Event()
    task = asyncio.create_task(
        run_worker(
            queue=queue,
            session_factory=factory,
            oth_client=oth_client,
            scrape_session=session,
            concurrency=concurrency,
            poll_interval_s=poll_interval_s,
            shutdown_grace_s=5.0,
            install_signal_handlers=False,
            shutdown_event=shutdown,
            soft_expiry_sweep=soft_expiry_sweep,
        )
    )
    return task, shutdown


async def _stop_worker(
    task: asyncio.Task, shutdown: asyncio.Event, session: StubScrapeSession
) -> None:
    shutdown.set()
    try:
        await asyncio.wait_for(task, timeout=10.0)
    finally:
        await session.close()


# ---- tests ----------------------------------------------------------------


async def test_drains_all_jobs_then_exits_on_shutdown_signal(session_factory):
    """AC: worker drains N queued jobs to `succeeded` and exits on shutdown.

    Stands in for the SIGTERM path: the runner's signal handler simply
    sets `shutdown_event`; we drive the same event directly so the test
    is portable across CI sandboxes that strip signal delivery.
    """
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    await _enqueue(queue, suburb_id, n=3)

    async def behavior(*_a, **_kw):
        return _empty_page()

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "succeeded", 3)
    finally:
        await _stop_worker(task, shutdown, session)

    assert task.done() and task.exception() is None
    assert await _count_status(session_factory, "queued") == 0
    assert await _count_status(session_factory, "running") == 0
    assert len(sweep.calls) == 3


async def test_concurrency_three_jobs_progress_in_parallel(session_factory):
    """AC: WORKER_CONCURRENCY=3 → three claimers active simultaneously."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    await _enqueue(queue, suburb_id, n=3)

    in_flight = 0
    saw_three = asyncio.Event()
    release = asyncio.Event()
    lock = asyncio.Lock()

    async def behavior(*_a, **_kw):
        nonlocal in_flight
        async with lock:
            in_flight += 1
            if in_flight >= 3:
                saw_three.set()
        await release.wait()
        return _empty_page()

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=3,
    )

    try:
        # Three workers must reach the same in-flight checkpoint at once.
        await asyncio.wait_for(saw_three.wait(), timeout=5.0)
        release.set()
        await _wait_until_status_count(session_factory, "succeeded", 3)
    finally:
        await _stop_worker(task, shutdown, session)

    assert in_flight == 3
    assert len(sweep.calls) == 3


async def test_transient_error_requeues_then_succeeds(session_factory):
    """AC: 5xx → requeue → second attempt succeeds → `succeeded`."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    [job_id] = await _enqueue(queue, suburb_id, n=1)

    attempts = 0

    async def behavior(*_a, **_kw):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _http_error(503)
        return _empty_page()

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "succeeded", 1)
    finally:
        await _stop_worker(task, shutdown, session)

    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT status, attempts, last_error_class "
                    "FROM scrape_job WHERE id = :id"
                ),
                {"id": job_id},
            )
        ).one()
    assert row.status == "succeeded"
    assert row.attempts == 1, "transient retry must increment attempts once"
    assert row.last_error_class == "transient"
    # Sweep runs only on the successful run, never after the failed one.
    assert len(sweep.calls) == 1


async def test_antibot_rotates_session_then_dead_letters_after_one_retry(
    session_factory,
):
    """AC: AntiBotError → session.rotate() → retry once → still fails → dead-letter."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    [job_id] = await _enqueue(queue, suburb_id, n=1)

    async def behavior(*_a, **_kw):
        raise AntiBotError("blocked", status_code=403)

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "deadletter", 1)
    finally:
        await _stop_worker(task, shutdown, session)

    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT status, attempts, last_error_class "
                    "FROM scrape_job WHERE id = :id"
                ),
                {"id": job_id},
            )
        ).one()
    assert row.status == "deadletter"
    assert row.attempts == 2, "anti-bot allows one retry before dead-letter"
    assert row.last_error_class == "antibot"
    # Rotate once per anti-bot failure; max_retries_antibot=1 → 2 fails.
    assert session.rotate_calls == 2
    # No success → no soft-expiry sweep.
    assert sweep.calls == []


async def test_parse_error_dead_letters_immediately(session_factory):
    """AC: ParseError → status=deadletter, attempts=1 (no retry)."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    [job_id] = await _enqueue(queue, suburb_id, n=1)

    async def behavior(*_a, **_kw):
        raise ParseError("malformed content[]")

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "deadletter", 1)
    finally:
        await _stop_worker(task, shutdown, session)

    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT status, attempts, last_error_class "
                    "FROM scrape_job WHERE id = :id"
                ),
                {"id": job_id},
            )
        ).one()
    assert row.status == "deadletter"
    assert row.attempts == 1
    assert row.last_error_class == "parse"
    assert sweep.calls == [], "sweep must not run on a failed job"


async def test_soft_expiry_sweep_invoked_only_on_successful_jobs(
    session_factory,
):
    """AC: soft-expiry sweep runs once per success, never on a failed job."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    success_id, fail_id = await _enqueue(queue, suburb_id, n=2)

    async def behavior(suburb, category, filters, page):
        # The first ID enqueued (lower id) succeeds; the second always
        # parse-errors and dead-letters on the first attempt.
        # We can't see job id from inside search, so we differentiate by
        # call count: first call = success, all subsequent = failure.
        # But two jobs run in parallel — keep concurrency=1 to make this
        # deterministic.
        return _empty_page()

    # Use a stateful behavior keyed by suburb_id — both jobs share suburb,
    # so route by call counter.
    counter = {"n": 0}

    async def routed_behavior(*_a, **_kw):
        counter["n"] += 1
        if counter["n"] == 1:
            return _empty_page()
        raise ParseError("forced failure on second job")

    oth = StubOTHClient(routed_behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "succeeded", 1)
        await _wait_until_status_count(session_factory, "deadletter", 1)
    finally:
        await _stop_worker(task, shutdown, session)

    # Sweep invoked exactly once — for the successful job, not the dead-lettered one.
    assert len(sweep.calls) == 1
    assert sweep.calls[0][1] is Category.FORSALE


async def test_workers_do_not_double_claim_jobs(session_factory):
    """AC reassertion: with N workers and N jobs, every job is claimed
    exactly once; the queue's SKIP LOCKED is honoured at the worker layer."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    job_ids = await _enqueue(queue, suburb_id, n=6)

    seen: list[int] = []
    seen_lock = asyncio.Lock()

    async def behavior(suburb, category, filters, page):
        return _empty_page()

    # Wrap StubOTHClient to track which job-equivalent (by call order)
    # was processed; because each job triggers exactly one search() call,
    # the count of distinct successes equals the count of jobs run.
    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=3,
    )

    try:
        await _wait_until_status_count(session_factory, "succeeded", len(job_ids))
    finally:
        await _stop_worker(task, shutdown, session)

    # Every job ended up succeeded with attempts==0 (no failure path).
    async with session_factory() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, status, attempts FROM scrape_job ORDER BY id"
                )
            )
        ).all()
    assert [r.status for r in rows] == ["succeeded"] * len(job_ids)
    assert all(r.attempts == 0 for r in rows)
    # search() must have been called exactly once per job.
    assert len(oth.calls) == len(job_ids)


async def test_paginates_until_has_next_false(session_factory):
    """`run_job` must keep calling `search()` while `has_next` is True
    and reconcile every page before invoking the soft-expiry sweep."""
    suburb_id = await _seed_suburb(session_factory)
    queue = _make_queue(session_factory)
    await _enqueue(queue, suburb_id, n=1)

    pages_seen: list[int] = []

    async def behavior(suburb, category, filters, page):
        pages_seen.append(page)
        if page < 2:
            return SearchPage(
                listings=[], raw_payloads=[], total=0, page=page, has_next=True
            )
        return SearchPage(
            listings=[], raw_payloads=[], total=0, page=page, has_next=False
        )

    oth = StubOTHClient(behavior)
    session = StubScrapeSession()
    sweep = _SoftExpirySpy()

    task, shutdown = await _start_worker(
        queue=queue,
        factory=session_factory,
        oth_client=oth,
        session=session,
        soft_expiry_sweep=sweep,
        concurrency=1,
    )

    try:
        await _wait_until_status_count(session_factory, "succeeded", 1)
    finally:
        await _stop_worker(task, shutdown, session)

    assert pages_seen == [0, 1, 2]
    assert len(sweep.calls) == 1
