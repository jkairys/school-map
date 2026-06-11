"""Integration tests for SuburbSummaryService and GET /suburbs/{id}/summary.

All tests run against a real Postgres test container (see conftest).

Coverage matrix (acceptance criteria):
- no runs → last_completed_run=None, in_flight_run=None, all zeros
- one completed run with mixed new/changed snapshots in all three categories
- in-flight run alongside a prior completed run → both returned
- empty window (no snapshots within run window) → all-zero deltas
- NULL prices excluded from medians (n reflects contributing listings only)
- sold listing outside 30-day window not counted in sold_30d median
- 404 for unknown suburb
- Router integration: GET /suburbs/{id}/summary happy path
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.db.models import (
    Listing,
    ListingSnapshot,
    Property,
    ScrapeJob,
    ScrapeRun,
    Suburb,
)
from listings_scraper.services.suburb_summary import SuburbSummaryService


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

_NOW = datetime.now(timezone.utc)
_YESTERDAY = _NOW - timedelta(days=1)
_2H_AGO = _NOW - timedelta(hours=2)
_1H_AGO = _NOW - timedelta(hours=1)
_31D_AGO = _NOW - timedelta(days=31)


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
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
                slug=f"{name.lower().replace(' ', '-')}-{state.lower()}-{postcode}",
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_property(
    factory: async_sessionmaker[AsyncSession],
    suburb_id: int,
    address: str = "1 Test St",
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Property(
                formatted_address=address,
                postcode="4064",
                suburb_id=suburb_id,
                first_seen_at=_NOW,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_listing(
    factory: async_sessionmaker[AsyncSession],
    property_id: int,
    suburb_id: int,
    category: str = "forsale",
    closed_at: datetime | None = None,
    sale_date: date | None = None,
) -> int:
    async with factory() as session:
        async with session.begin():
            row = Listing(
                property_id=property_id,
                suburb_id=suburb_id,
                category=category,
                first_seen_at=_NOW,
                last_seen_at=_NOW,
                closed_at=closed_at,
                sale_date=sale_date,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_snapshot(
    factory: async_sessionmaker[AsyncSession],
    listing_id: int,
    observed_at: datetime,
    price: int | None = None,
    is_initial: bool = True,
) -> int:
    changed_fields = ["__initial__"] if is_initial else ["price"]
    async with factory() as session:
        async with session.begin():
            row = ListingSnapshot(
                listing_id=listing_id,
                observed_at=observed_at,
                price=price,
                raw_payload={},
                changed_fields=changed_fields,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_run(
    factory: async_sessionmaker[AsyncSession],
    triggered_at: datetime | None = None,
    status: str = "running",
) -> int:
    if triggered_at is None:
        triggered_at = _2H_AGO
    async with factory() as session:
        async with session.begin():
            row = ScrapeRun(
                trigger_source="api",
                filters_snapshot={},
                status=status,
                triggered_at=triggered_at,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_job(
    factory: async_sessionmaker[AsyncSession],
    run_id: int,
    suburb_id: int,
    category: str = "forsale",
    status: str = "succeeded",
    completed_at: datetime | None = None,
) -> int:
    if status in ("succeeded", "failed", "deadletter") and completed_at is None:
        completed_at = _1H_AGO
    async with factory() as session:
        async with session.begin():
            row = ScrapeJob(
                run_id=run_id,
                suburb_id=suburb_id,
                category=category,
                filters={},
                status=status,
                attempts=0,
                completed_at=completed_at,
            )
            session.add(row)
            await session.flush()
            return row.id


# ------------------------------------------------------------------ #
# Tests                                                               #
# ------------------------------------------------------------------ #


async def test_unknown_suburb_returns_none(session_factory) -> None:
    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(999_999)
    assert result is None


async def test_no_runs_returns_nulls_and_zeros(session_factory) -> None:
    suburb_id = await _seed_suburb(session_factory, "Noosa")

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    assert result.id == suburb_id
    assert result.name == "Noosa"
    assert result.last_completed_run is None
    assert result.in_flight_run is None

    assert result.deltas.forsale.new == 0
    assert result.deltas.forsale.changed == 0
    assert result.deltas.forrent.new == 0
    assert result.deltas.recentlysold.new == 0

    assert result.totals.forsale == 0
    assert result.totals.forrent == 0
    assert result.totals.recentlysold == 0

    assert result.medians.sold_30d.value is None
    assert result.medians.sold_30d.n == 0
    assert result.medians.asking.value is None
    assert result.medians.rent.value is None


async def test_one_completed_run_with_mixed_new_changed_snapshots(session_factory) -> None:
    """One run, all jobs terminal; snapshots in window with new and changed per category."""
    suburb_id = await _seed_suburb(session_factory, "Maroochydore")
    run_id = await _seed_run(session_factory, triggered_at=_2H_AGO)

    # Seed jobs for all three categories — completed 1 hour ago.
    for cat in ("forsale", "forrent", "recentlysold"):
        await _seed_job(
            session_factory,
            run_id=run_id,
            suburb_id=suburb_id,
            category=cat,
            status="succeeded",
            completed_at=_1H_AGO,
        )

    # Manually update scrape_run.status to 'succeeded' + completed_at
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE scrape_run SET status='succeeded', completed_at=:ca WHERE id=:rid"
                ),
                {"ca": _1H_AGO, "rid": run_id},
            )

    # Seed properties + listings + snapshots for each category.
    # forsale: 2 new + 1 changed
    for i in range(3):
        prop_id = await _seed_property(session_factory, suburb_id, f"For Sale St {i}")
        listing_id = await _seed_listing(
            session_factory, prop_id, suburb_id, "forsale"
        )
        is_initial = i < 2  # first two are new, last is changed
        await _seed_snapshot(
            session_factory,
            listing_id,
            observed_at=_1H_AGO,  # within window [_2H_AGO, _1H_AGO]
            price=500_000 + i * 50_000,
            is_initial=is_initial,
        )

    # forrent: 1 new + 1 changed
    for i in range(2):
        prop_id = await _seed_property(session_factory, suburb_id, f"For Rent St {i}")
        listing_id = await _seed_listing(
            session_factory, prop_id, suburb_id, "forrent"
        )
        await _seed_snapshot(
            session_factory,
            listing_id,
            observed_at=_1H_AGO,
            price=600 + i * 50,
            is_initial=(i == 0),
        )

    # recentlysold: 2 new
    today = date.today()
    for i in range(2):
        prop_id = await _seed_property(session_factory, suburb_id, f"Sold St {i}")
        listing_id = await _seed_listing(
            session_factory,
            prop_id,
            suburb_id,
            "recentlysold",
            sale_date=today - timedelta(days=i),
        )
        await _seed_snapshot(
            session_factory,
            listing_id,
            observed_at=_1H_AGO,
            price=700_000 + i * 100_000,
            is_initial=True,
        )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    assert result.last_completed_run is not None
    assert result.last_completed_run.id == run_id
    assert result.last_completed_run.completed_at is not None
    assert result.in_flight_run is None

    # Deltas
    assert result.deltas.forsale.new == 2
    assert result.deltas.forsale.changed == 1
    assert result.deltas.forrent.new == 1
    assert result.deltas.forrent.changed == 1
    assert result.deltas.recentlysold.new == 2
    assert result.deltas.recentlysold.changed == 0

    # Totals
    assert result.totals.forsale == 3
    assert result.totals.forrent == 2
    assert result.totals.recentlysold == 2


async def test_in_flight_run_alongside_prior_completed_run(session_factory) -> None:
    """Both a completed run and an in-flight run exist; both are returned."""
    suburb_id = await _seed_suburb(session_factory, "Caloundra")

    # First run: completed two hours ago.
    run1_id = await _seed_run(
        session_factory, triggered_at=_NOW - timedelta(hours=3)
    )
    await _seed_job(
        session_factory,
        run_id=run1_id,
        suburb_id=suburb_id,
        category="forsale",
        status="succeeded",
        completed_at=_2H_AGO,
    )
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE scrape_run SET status='succeeded', completed_at=:ca WHERE id=:rid"
                ),
                {"ca": _2H_AGO, "rid": run1_id},
            )

    # Second run: in-flight (queued job).
    run2_id = await _seed_run(session_factory, triggered_at=_NOW - timedelta(minutes=5))
    await _seed_job(
        session_factory,
        run_id=run2_id,
        suburb_id=suburb_id,
        category="forsale",
        status="queued",
        completed_at=None,
    )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    assert result.last_completed_run is not None
    assert result.last_completed_run.id == run1_id
    assert result.in_flight_run is not None
    assert result.in_flight_run.id == run2_id


async def test_empty_window_all_zero_deltas(session_factory) -> None:
    """Snapshots exist but none fall within the completed run window → all zero deltas."""
    suburb_id = await _seed_suburb(session_factory, "Coolum Beach")

    # Run window: 2h ago → 1h ago
    run_id = await _seed_run(session_factory, triggered_at=_2H_AGO)
    await _seed_job(
        session_factory,
        run_id=run_id,
        suburb_id=suburb_id,
        category="forsale",
        status="succeeded",
        completed_at=_1H_AGO,
    )

    # Snapshot OUTSIDE the window (way in the past, before run started).
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(session_factory, prop_id, suburb_id, "forsale")
    await _seed_snapshot(
        session_factory,
        listing_id,
        observed_at=_NOW - timedelta(hours=10),  # before run started
        price=400_000,
        is_initial=True,
    )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    assert result.last_completed_run is not None
    assert result.deltas.forsale.new == 0
    assert result.deltas.forsale.changed == 0


async def test_null_prices_excluded_from_medians(session_factory) -> None:
    """Snapshots with NULL price are excluded; n reflects only price-bearing listings."""
    suburb_id = await _seed_suburb(session_factory, "Alexandra Headland")

    # One forsale listing with a price, one without.
    for i, price in enumerate([None, 800_000]):
        prop_id = await _seed_property(session_factory, suburb_id, f"Null Price St {i}")
        listing_id = await _seed_listing(
            session_factory, prop_id, suburb_id, "forsale"
        )
        await _seed_snapshot(
            session_factory, listing_id, observed_at=_NOW, price=price, is_initial=True
        )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    # Only the 800_000 listing should count.
    assert result.medians.asking.n == 1
    assert result.medians.asking.value == 800_000


async def test_sold_listing_outside_30d_window_not_counted(session_factory) -> None:
    """A recentlysold listing whose sale_date is > 30 days ago is excluded from sold_30d."""
    suburb_id = await _seed_suburb(session_factory, "Peregian Beach")
    today = date.today()

    # One listing sold 10 days ago (in window), one sold 31 days ago (outside).
    prices_and_dates = [
        (900_000, today - timedelta(days=10)),   # inside window
        (1_100_000, today - timedelta(days=31)),  # outside window
    ]
    for i, (price, sale_date) in enumerate(prices_and_dates):
        prop_id = await _seed_property(session_factory, suburb_id, f"Sold {i}")
        listing_id = await _seed_listing(
            session_factory,
            prop_id,
            suburb_id,
            "recentlysold",
            sale_date=sale_date,
        )
        await _seed_snapshot(
            session_factory, listing_id, observed_at=_NOW, price=price, is_initial=True
        )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    # Only the 900_000 listing should contribute.
    assert result.medians.sold_30d.n == 1
    assert result.medians.sold_30d.value == 900_000


async def test_sold_30d_uses_first_snapshot_per_listing(session_factory) -> None:
    """For sold_30d, the FIRST snapshot per listing provides the canonical price."""
    suburb_id = await _seed_suburb(session_factory, "Mooloolaba")
    today = date.today()

    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory,
        prop_id,
        suburb_id,
        "recentlysold",
        sale_date=today - timedelta(days=5),
    )

    # First snapshot (canonical sale price): 500_000 observed 2h ago
    await _seed_snapshot(
        session_factory,
        listing_id,
        observed_at=_2H_AGO,
        price=500_000,
        is_initial=True,
    )
    # Later snapshot with different price: 550_000 observed 1h ago
    await _seed_snapshot(
        session_factory,
        listing_id,
        observed_at=_1H_AGO,
        price=550_000,
        is_initial=False,
    )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    # First snapshot wins → 500_000
    assert result.medians.sold_30d.n == 1
    assert result.medians.sold_30d.value == 500_000


async def test_asking_uses_latest_snapshot_active_only(session_factory) -> None:
    """Asking median uses latest snapshot; closed listings are excluded."""
    suburb_id = await _seed_suburb(session_factory, "Bli Bli")

    # Open listing — latest price 800_000
    prop1_id = await _seed_property(session_factory, suburb_id, "Open St")
    open_listing_id = await _seed_listing(
        session_factory, prop1_id, suburb_id, "forsale"
    )
    await _seed_snapshot(
        session_factory, open_listing_id, observed_at=_2H_AGO, price=700_000, is_initial=True
    )
    await _seed_snapshot(
        session_factory, open_listing_id, observed_at=_1H_AGO, price=800_000, is_initial=False
    )

    # Closed listing — should be excluded from asking
    prop2_id = await _seed_property(session_factory, suburb_id, "Closed St")
    closed_listing_id = await _seed_listing(
        session_factory,
        prop2_id,
        suburb_id,
        "forsale",
        closed_at=_1H_AGO,
    )
    await _seed_snapshot(
        session_factory,
        closed_listing_id,
        observed_at=_2H_AGO,
        price=1_000_000,
        is_initial=True,
    )

    async with session_factory() as session:
        svc = SuburbSummaryService(session)
        result = await svc.summary(suburb_id)

    assert result is not None
    # Only the open listing's latest price (800_000) should contribute.
    assert result.medians.asking.n == 1
    assert result.medians.asking.value == 800_000


# ------------------------------------------------------------------ #
# Router / HTTP tests                                                 #
# ------------------------------------------------------------------ #


@pytest_asyncio.fixture
async def api_client(session_factory):
    """HTTP client wired to the FastAPI app with the test-container session."""
    from listings_scraper.api.app import app
    from listings_scraper.db.engine import get_db

    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_summary_endpoint_404_for_unknown_suburb(api_client) -> None:
    r = await api_client.get("/suburbs/999999/summary")
    assert r.status_code == 404


async def test_summary_endpoint_200_with_data(api_client, session_factory) -> None:
    """Happy-path HTTP test: one suburb, no runs → all-zeros DTO returned."""
    suburb_id = await _seed_suburb(session_factory, "Wurtulla", postcode="4575")

    r = await api_client.get(f"/suburbs/{suburb_id}/summary")
    assert r.status_code == 200

    body = r.json()
    assert body["id"] == suburb_id
    assert body["name"] == "Wurtulla"
    assert body["postcode"] == "4575"
    assert body["state"] == "QLD"
    assert body["last_completed_run"] is None
    assert body["in_flight_run"] is None
    assert body["totals"]["forsale"] == 0
    assert body["medians"]["sold_30d"]["value"] is None
    assert body["medians"]["sold_30d"]["n"] == 0
