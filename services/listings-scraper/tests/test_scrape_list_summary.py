"""Integration tests for ScrapeListSummaryService.summary().

Exercises against a real Postgres test container (see conftest).
Tests all acceptance criteria:

- Empty list (no suburbs) → zero counts, no latest_run.
- List with suburbs but no runs → counts from properties/listings, no latest_run.
- List with one completed run → latest_run is that run, in_flight=False.
- List with one in-flight run → status='running', in_flight=True.
- List with multiple runs → latest_run is the most recent by triggered_at.
- properties_observed counts DISTINCT property.id across suburbs in the area.
- active_listings correct splits; closed listings excluded.
- GET /scrape-lists/{id}/summary returns 200 with correct shape.
- GET /scrape-lists/{id}/summary returns 404 for missing list.
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.api.app import app
from listings_scraper.db.engine import get_db
from listings_scraper.db.models import (
    Listing,
    Property,
    ScrapeJob,
    ScrapeList,
    ScrapeListSuburb,
    ScrapeRun,
    Suburb,
)
from listings_scraper.services.scrape_list_summary import ScrapeListSummaryService


# ------------------------------------------------------------------ #
# helpers                                                             #
# ------------------------------------------------------------------ #


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Paddington",
    postcode: str = "4064",
    state: str = "QLD",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state=state,
                slug=f"{name.lower().replace(' ', '-')}-qld-{postcode}",
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_list(
    factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "test-list",
    suburb_ids: list[int] | None = None,
) -> int:
    async with factory() as session:
        async with session.begin():
            row = ScrapeList(
                name=name,
                description=None,
                filters={},
                cron_schedule=None,
            )
            session.add(row)
            await session.flush()
            list_id = row.id
            for sid in suburb_ids or []:
                session.add(ScrapeListSuburb(scrape_list_id=list_id, suburb_id=sid))
            await session.flush()
            return list_id


async def _seed_run(
    factory: async_sessionmaker[AsyncSession],
    *,
    list_id: int,
    status: str = "running",
    triggered_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> int:
    async with factory() as session:
        async with session.begin():
            row = ScrapeRun(
                scrape_list_id=list_id,
                trigger_source="api",
                filters_snapshot={},
                status=status,
                completed_at=completed_at,
            )
            session.add(row)
            await session.flush()
            run_id = row.id
            if triggered_at is not None:
                # Override the server-default triggered_at for ordering tests.
                await session.execute(
                    text(
                        "UPDATE scrape_run SET triggered_at = :ts WHERE id = :id"
                    ),
                    {"ts": triggered_at, "id": run_id},
                )
            return run_id


async def _seed_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    run_id: int,
    list_id: int | None = None,
    suburb_id: int | None = None,
    status: str = "queued",
) -> int:
    async with factory() as session:
        async with session.begin():
            completed_at = None
            if status in ("succeeded", "failed", "deadletter"):
                completed_at = datetime.now(timezone.utc)
            row = ScrapeJob(
                run_id=run_id,
                scrape_list_id=list_id,
                suburb_id=suburb_id,
                category="forsale",
                filters={},
                status=status,
                attempts=0,
                completed_at=completed_at,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_property(
    factory: async_sessionmaker[AsyncSession],
    *,
    suburb_id: int,
    address: str = "1 Test St",
    postcode: str = "4064",
    external_property_id: str | None = None,
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Property(
                external_property_id=external_property_id,
                formatted_address=address,
                postcode=postcode,
                suburb_id=suburb_id,
                location=None,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_listing(
    factory: async_sessionmaker[AsyncSession],
    *,
    property_id: int,
    suburb_id: int,
    category: str = "forsale",
    closed_at: datetime | None = None,
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Listing(
                property_id=property_id,
                suburb_id=suburb_id,
                category=category,
                external_listing_id=None,
                closed_at=closed_at,
            )
            session.add(row)
            await session.flush()
            return row.id


# ------------------------------------------------------------------ #
# API client fixture                                                   #
# ------------------------------------------------------------------ #


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
# service-layer tests                                                  #
# ------------------------------------------------------------------ #


async def test_summary_raises_for_missing_list(session_factory) -> None:
    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        from listings_scraper.services.scrape_list import ScrapeListNotFoundError

        with pytest.raises(ScrapeListNotFoundError):
            await svc.summary(999_999)


async def test_summary_empty_list_no_suburbs(session_factory) -> None:
    """A list with no suburbs returns zeros and no latest_run."""
    list_id = await _seed_list(session_factory, suburb_ids=[])

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.id == list_id
    assert result.suburb_count == 0
    assert result.properties_observed == 0
    assert result.active_listings.forsale == 0
    assert result.active_listings.forrent == 0
    assert result.active_listings.recentlysold == 0
    assert result.latest_run is None
    assert result.in_flight is False


async def test_summary_suburbs_no_runs(session_factory) -> None:
    """List with suburbs but no runs: counts come from data, no latest_run."""
    sub_a = await _seed_suburb(session_factory, name="Alpha", postcode="4000")
    sub_b = await _seed_suburb(session_factory, name="Beta", postcode="4001")
    list_id = await _seed_list(session_factory, suburb_ids=[sub_a, sub_b])

    # Seed properties and listings
    prop_a1 = await _seed_property(
        session_factory, suburb_id=sub_a, address="1 Alpha St", postcode="4000",
        external_property_id="P-A1"
    )
    prop_a2 = await _seed_property(
        session_factory, suburb_id=sub_a, address="2 Alpha St", postcode="4000",
        external_property_id="P-A2"
    )
    prop_b1 = await _seed_property(
        session_factory, suburb_id=sub_b, address="1 Beta St", postcode="4001",
        external_property_id="P-B1"
    )
    await _seed_listing(session_factory, property_id=prop_a1, suburb_id=sub_a, category="forsale")
    await _seed_listing(session_factory, property_id=prop_a2, suburb_id=sub_a, category="forrent")
    await _seed_listing(session_factory, property_id=prop_b1, suburb_id=sub_b, category="recentlysold")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.suburb_count == 2
    assert result.properties_observed == 3
    assert result.active_listings.forsale == 1
    assert result.active_listings.forrent == 1
    assert result.active_listings.recentlysold == 1
    assert result.latest_run is None
    assert result.in_flight is False


async def test_summary_properties_observed_distinct_across_suburbs(
    session_factory,
) -> None:
    """2 props in suburb A + 1 in suburb B → properties_observed = 3."""
    sub_a = await _seed_suburb(session_factory, name="SubA", postcode="5000")
    sub_b = await _seed_suburb(session_factory, name="SubB", postcode="5001")
    list_id = await _seed_list(session_factory, suburb_ids=[sub_a, sub_b])

    # 2 properties in A, 1 in B
    await _seed_property(
        session_factory, suburb_id=sub_a, address="1 A St", postcode="5000",
        external_property_id="PA1"
    )
    await _seed_property(
        session_factory, suburb_id=sub_a, address="2 A St", postcode="5000",
        external_property_id="PA2"
    )
    await _seed_property(
        session_factory, suburb_id=sub_b, address="1 B St", postcode="5001",
        external_property_id="PB1"
    )

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.properties_observed == 3


async def test_summary_active_listings_excludes_closed(session_factory) -> None:
    """Closed listings (closed_at IS NOT NULL) are excluded from active_listings."""
    sub = await _seed_suburb(session_factory, name="Closedville", postcode="6000")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    prop1 = await _seed_property(
        session_factory, suburb_id=sub, address="1 C St", postcode="6000",
        external_property_id="PC1"
    )
    prop2 = await _seed_property(
        session_factory, suburb_id=sub, address="2 C St", postcode="6000",
        external_property_id="PC2"
    )
    prop3 = await _seed_property(
        session_factory, suburb_id=sub, address="3 C St", postcode="6000",
        external_property_id="PC3"
    )

    # One open forsale
    await _seed_listing(session_factory, property_id=prop1, suburb_id=sub, category="forsale")
    # One closed forsale — should not appear in active count
    await _seed_listing(
        session_factory,
        property_id=prop2,
        suburb_id=sub,
        category="forsale",
        closed_at=datetime.now(timezone.utc),
    )
    # One open forrent
    await _seed_listing(session_factory, property_id=prop3, suburb_id=sub, category="forrent")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.active_listings.forsale == 1  # closed one excluded
    assert result.active_listings.forrent == 1
    assert result.active_listings.recentlysold == 0


async def test_summary_active_listings_absent_categories_are_zero(
    session_factory,
) -> None:
    """Categories not present in DB still return 0 (not KeyError)."""
    sub = await _seed_suburb(session_factory, name="Zeroton", postcode="7000")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    prop = await _seed_property(
        session_factory, suburb_id=sub, address="1 Z St", postcode="7000",
        external_property_id="PZ1"
    )
    # Only forsale; forrent and recentlysold absent.
    await _seed_listing(session_factory, property_id=prop, suburb_id=sub, category="forsale")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.active_listings.forsale == 1
    assert result.active_listings.forrent == 0
    assert result.active_listings.recentlysold == 0


async def test_summary_one_completed_run(session_factory) -> None:
    """latest_run is the completed run; in_flight=False."""
    sub = await _seed_suburb(session_factory, name="Runtown", postcode="8000")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    run_id = await _seed_run(
        session_factory,
        list_id=list_id,
        status="succeeded",
        completed_at=datetime.now(timezone.utc),
    )
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="succeeded")
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="succeeded")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.latest_run is not None
    assert result.latest_run.id == run_id
    assert result.latest_run.status == "succeeded"
    assert result.latest_run.completed_at is not None
    assert result.latest_run.counts.succeeded == 2
    assert result.latest_run.counts.queued == 0
    assert result.in_flight is False


async def test_summary_one_inflight_run(session_factory) -> None:
    """latest_run with status='running' → in_flight=True, completed_at=None."""
    sub = await _seed_suburb(session_factory, name="Flightsville", postcode="9000")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    run_id = await _seed_run(session_factory, list_id=list_id, status="running")
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="running")
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="queued")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.latest_run is not None
    assert result.latest_run.status == "running"
    assert result.latest_run.completed_at is None
    assert result.latest_run.counts.running == 1
    assert result.latest_run.counts.queued == 1
    assert result.in_flight is True


async def test_summary_multiple_runs_latest_by_triggered_at(
    session_factory,
) -> None:
    """When multiple runs exist, latest_run is the one with the most recent triggered_at."""
    sub = await _seed_suburb(session_factory, name="Multirun", postcode="1111")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])

    old_ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    new_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    old_run_id = await _seed_run(
        session_factory,
        list_id=list_id,
        status="succeeded",
        triggered_at=old_ts,
        completed_at=datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    new_run_id = await _seed_run(
        session_factory,
        list_id=list_id,
        status="running",
        triggered_at=new_ts,
    )

    # Each run needs at least one job (FK constraint).
    await _seed_job(session_factory, run_id=old_run_id, list_id=list_id, status="succeeded")
    await _seed_job(session_factory, run_id=new_run_id, list_id=list_id, status="running")

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.latest_run is not None
    assert result.latest_run.id == new_run_id
    assert result.in_flight is True


async def test_summary_job_counts_all_statuses(session_factory) -> None:
    """latest_run.counts reflects all five job statuses correctly."""
    sub = await _seed_suburb(session_factory, name="Countville", postcode="2222")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    run_id = await _seed_run(session_factory, list_id=list_id, status="partial")
    completed_at = datetime.now(timezone.utc)

    for status in ("queued", "running", "succeeded", "failed", "deadletter"):
        await _seed_job(
            session_factory, run_id=run_id, list_id=list_id, status=status
        )

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.latest_run is not None
    c = result.latest_run.counts
    assert c.queued == 1
    assert c.running == 1
    assert c.succeeded == 1
    assert c.failed == 1
    assert c.deadletter == 1


async def test_summary_trigger_source_passthrough(session_factory) -> None:
    """trigger_source is correctly passed through to LatestRunSummary."""
    sub = await _seed_suburb(session_factory, name="CLIton", postcode="3333")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])

    async with session_factory() as session:
        async with session.begin():
            run = ScrapeRun(
                scrape_list_id=list_id,
                trigger_source="cli",
                filters_snapshot={},
                status="running",
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            session.add(ScrapeJob(
                run_id=run_id,
                scrape_list_id=list_id,
                category="forsale",
                filters={},
                status="queued",
                attempts=0,
            ))

    async with session_factory() as session:
        svc = ScrapeListSummaryService(session)
        result = await svc.summary(list_id)

    assert result.latest_run is not None
    assert result.latest_run.trigger_source == "cli"


# ------------------------------------------------------------------ #
# REST endpoint tests                                                  #
# ------------------------------------------------------------------ #


async def test_api_summary_404_for_missing_list(api_client) -> None:
    r = await api_client.get("/scrape-lists/999999/summary")
    assert r.status_code == 404


async def test_api_summary_empty_list(api_client, session_factory) -> None:
    """GET /scrape-lists/{id}/summary returns a valid 200 for an empty list."""
    list_id = await _seed_list(session_factory, suburb_ids=[])
    r = await api_client.get(f"/scrape-lists/{list_id}/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == list_id
    assert body["suburb_count"] == 0
    assert body["properties_observed"] == 0
    assert body["active_listings"] == {
        "forsale": 0,
        "forrent": 0,
        "recentlysold": 0,
    }
    assert body["latest_run"] is None
    assert body["in_flight"] is False


async def test_api_summary_with_run(api_client, session_factory) -> None:
    """GET /scrape-lists/{id}/summary reflects the latest run in the response."""
    sub = await _seed_suburb(session_factory, name="APItown", postcode="4444")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    run_id = await _seed_run(
        session_factory,
        list_id=list_id,
        status="succeeded",
        completed_at=datetime.now(timezone.utc),
    )
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="succeeded")

    r = await api_client.get(f"/scrape-lists/{list_id}/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["latest_run"] is not None
    assert body["latest_run"]["id"] == run_id
    assert body["latest_run"]["status"] == "succeeded"
    assert body["in_flight"] is False


async def test_api_summary_inflight(api_client, session_factory) -> None:
    """GET /scrape-lists/{id}/summary: in_flight=true when status=running."""
    sub = await _seed_suburb(session_factory, name="Flightsapi", postcode="5555")
    list_id = await _seed_list(session_factory, suburb_ids=[sub])
    run_id = await _seed_run(session_factory, list_id=list_id, status="running")
    await _seed_job(session_factory, run_id=run_id, list_id=list_id, status="running")

    r = await api_client.get(f"/scrape-lists/{list_id}/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["in_flight"] is True
    assert body["latest_run"]["status"] == "running"
    assert body["latest_run"]["completed_at"] is None
