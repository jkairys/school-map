"""Live end-to-end smoke test against real OTH.

Skipped by default. Runs only when ``RUN_LIVE_OTH_TESTS=1`` is set in the
environment. Intended to be run manually before releases — never in CI.

The test:

1. Boots a fresh Postgres test container (reuses the project's
   ``session_factory`` fixture).
2. Mounts the FastAPI app over an ASGI transport, with the DB dependencies
   pointed at the test container.
3. Resolves a known small suburb (Mount Coolum QLD 4573) via the suburb
   resolver, attaches it to a freshly-created scrape list, and triggers
   ``POST /scrape-lists/{id}/run``.
4. Drives a real camoufox-backed ``ScrapeSession`` + ``OTHApiClient``
   through the worker loop until every job reaches a terminal state
   (``succeeded`` | ``failed`` | ``deadletter``) or the test timeout
   elapses.
5. Asserts at least one ``Listing`` was recorded with at least one
   ``ListingSnapshot``.

If the test fails it prints terminal job statuses and the last error per
dead-lettered/failed job — the difference between "OTH was down today,
retry" and "we have a real bug" at release time.

To run:

    RUN_LIVE_OTH_TESTS=1 uv run pytest \
        services/oth-scraper/tests/e2e/test_live_smoke.py -s
"""
import asyncio
import os
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

LIVE_FLAG = "RUN_LIVE_OTH_TESTS"

pytestmark = pytest.mark.skipif(
    os.environ.get(LIVE_FLAG) != "1",
    reason=f"set {LIVE_FLAG}=1 to run the live OTH smoke test",
)


# Mount Coolum is a small QLD coastal suburb that has consistently shown a
# handful of listings across all three categories during prior verification
# runs — small enough to keep the test fast, big enough that "zero results"
# would itself be a meaningful signal.
SUBURB_NAME = "Mount Coolum"
SUBURB_STATE = "QLD"
SUBURB_POSTCODE = "4573"

JOB_TERMINAL_TIMEOUT_SECONDS = 300.0  # 5 minutes
POLL_INTERVAL_SECONDS = 2.0


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    from oth_scraper.api.app import app
    from oth_scraper.db.engine import get_db, get_session_factory

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


async def _all_terminal(session_factory, list_id: int) -> tuple[bool, dict[str, int]]:
    """Return (all_terminal, status_counts) for jobs on ``list_id``."""
    from oth_scraper.db.models import ScrapeJob

    async with session_factory() as s:
        statuses = (
            (
                await s.execute(
                    select(ScrapeJob.status).where(
                        ScrapeJob.scrape_list_id == list_id
                    )
                )
            )
            .scalars()
            .all()
        )
    counts: dict[str, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    terminal = {"succeeded", "failed", "deadletter"}
    return bool(statuses) and all(s in terminal for s in statuses), counts


async def _print_job_diagnostics(session_factory, list_id: int) -> None:
    from oth_scraper.db.models import ScrapeJob

    async with session_factory() as s:
        rows = (
            await s.execute(
                select(
                    ScrapeJob.id,
                    ScrapeJob.suburb_id,
                    ScrapeJob.category,
                    ScrapeJob.status,
                    ScrapeJob.attempts,
                    ScrapeJob.last_error_class,
                    ScrapeJob.last_error_message,
                ).where(ScrapeJob.scrape_list_id == list_id)
            )
        ).all()

    print("\n=== live smoke job diagnostics ===")
    for r in rows:
        line = (
            f"  job={r.id} suburb={r.suburb_id} category={r.category} "
            f"status={r.status} attempts={r.attempts}"
        )
        if r.last_error_class or r.last_error_message:
            line += (
                f" last_error_class={r.last_error_class} "
                f"last_error_message={r.last_error_message!r}"
            )
        print(line)


async def _count_listings_and_snapshots(session_factory) -> tuple[int, int]:
    from sqlalchemy import func

    from oth_scraper.db.models import Listing, ListingSnapshot

    async with session_factory() as s:
        listings = (
            await s.execute(select(func.count()).select_from(Listing))
        ).scalar_one()
        snapshots = (
            await s.execute(select(func.count()).select_from(ListingSnapshot))
        ).scalar_one()
    return listings, snapshots


async def test_live_smoke_against_real_oth(
    api_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
):
    """End-to-end smoke: producer + worker + read API against live OTH."""
    from oth_scraper.queue import JobQueue
    from oth_scraper.scrape_session import ScrapeSession
    from oth_scraper.oth_client import OTHApiClient
    from oth_scraper.worker_loop import run_worker

    # 1. Create the list with a real filter applied (`beds_min=1`). The
    # initial run of this smoke test against live OTH discovered that the
    # original filter encoding in `oth_client/payload.py` was wrong — any
    # non-empty filter dimension produced a 400 "An unexpected error has
    # occurred" from OTH. The fix (separate PR) re-derived the filter
    # shape from the live frontend; we keep `beds_min=1` here as the
    # canary so any future regression on filter encoding fails this
    # smoke run loudly instead of silently 400-ing in production.
    create_resp = await api_client.post(
        "/scrape-lists",
        json={
            "name": "live-smoke",
            "description": "live OTH smoke (RUN_LIVE_OTH_TESTS=1)",
            "filters": {
                "beds_min": 1,
                "beds_max": None,
                "property_types": None,
                "price_min": None,
                "price_max": None,
            },
            "cron_schedule": None,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    list_id = create_resp.json()["id"]

    # 2. Resolve + attach the suburb. Postcode + state disambiguate so the
    # resolver doesn't return a candidate list.
    add_resp = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs",
        json={
            "name": SUBURB_NAME,
            "postcode": SUBURB_POSTCODE,
            "state": SUBURB_STATE,
        },
    )
    assert add_resp.status_code == 200, add_resp.text

    # 3. Trigger the producer fan-out.
    run_resp = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert run_resp.status_code == 200, run_resp.text
    run_body = run_resp.json()
    assert run_body["count"] == 3, run_body
    print(f"\nlive smoke: enqueued {run_body['count']} jobs for list {list_id}")

    # 4. Drive a real worker against real OTH until all jobs are terminal.
    queue = JobQueue(session_factory)
    scrape_session = ScrapeSession()
    oth_client = OTHApiClient()
    shutdown = asyncio.Event()

    worker = asyncio.create_task(
        run_worker(
            queue=queue,
            session_factory=session_factory,
            oth_client=oth_client,
            scrape_session=scrape_session,
            concurrency=1,
            poll_interval_s=1.0,
            shutdown_grace_s=15.0,
            install_signal_handlers=False,
            shutdown_event=shutdown,
        )
    )

    try:
        deadline = time.monotonic() + JOB_TERMINAL_TIMEOUT_SECONDS
        last_counts: dict[str, int] = {}
        while True:
            done, counts = await _all_terminal(session_factory, list_id)
            if counts != last_counts:
                print(f"live smoke: job status counts = {counts}")
                last_counts = counts
            if done:
                break
            if time.monotonic() > deadline:
                await _print_job_diagnostics(session_factory, list_id)
                listings, snapshots = await _count_listings_and_snapshots(
                    session_factory
                )
                print(
                    f"live smoke: timeout — listings={listings} snapshots={snapshots}"
                )
                pytest.fail(
                    f"jobs did not reach terminal state within "
                    f"{JOB_TERMINAL_TIMEOUT_SECONDS:.0f}s; counts={counts}"
                )
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        shutdown.set()
        try:
            await asyncio.wait_for(worker, timeout=20.0)
        except asyncio.TimeoutError:
            worker.cancel()
            try:
                await worker
            except (asyncio.CancelledError, Exception):
                pass
        await scrape_session.close()

    # 5. Always print job statuses and dataset size — the diff between
    # "OTH outage" and "real bug" at release time lives in this output.
    await _print_job_diagnostics(session_factory, list_id)
    listings, snapshots = await _count_listings_and_snapshots(session_factory)
    print(
        f"live smoke: recorded listings={listings} snapshots={snapshots}"
    )

    # 6. Assert acceptance criteria. We do NOT require all jobs to have
    # succeeded — recentlysold or forrent in a tiny coastal suburb may
    # legitimately come back empty — but at least one listing with at
    # least one snapshot must have been reconciled, and no job should be
    # dead-lettered without us screaming about it.
    assert listings >= 1, (
        "expected at least one Listing to be recorded against real OTH"
    )
    assert snapshots >= 1, (
        "expected at least one ListingSnapshot to be recorded"
    )

    # Surface dead-lettered jobs as a hard failure: a single category
    # blowing up is not an OTH outage, it's a regression.
    _, final_counts = await _all_terminal(session_factory, list_id)
    deadlettered = final_counts.get("deadletter", 0)
    assert deadlettered == 0, (
        f"{deadlettered} job(s) dead-lettered — see diagnostics above"
    )
