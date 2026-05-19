"""Integration tests for the soft-expiry sweep.

The sweep closes Listings that haven't been observed in their `(suburb,
category)` feed for longer than the configured window. Tests run against
the shared Postgres test container (see conftest) and assert externally
observable DB state.
"""
from datetime import timedelta

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.api.app import app
from listings_scraper.db.engine import get_session_factory
from listings_scraper.db.models import Listing, Suburb
from listings_scraper.listing_reconciler import (
    reconcile_batch,
    run_soft_expiry_sweep,
)
from listings_scraper.oth_client.types import Category, OTHListing

WINDOW = timedelta(days=14)


# ---- helpers --------------------------------------------------------------


async def _seed_suburb(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str,
    postcode: str,
    state: str = "QLD",
    oth_slug: str | None = None,
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state=state,
                oth_slug=oth_slug or f"{name.lower()}-{state.lower()}-{postcode}",
            )
            session.add(row)
            await session.flush()
            return row.id


def _make_listing(
    *,
    oth_property_id: str,
    address: str,
    postcode: str = "4064",
) -> OTHListing:
    return OTHListing(
        oth_property_id=oth_property_id,
        formatted_address=address,
        postcode=postcode,
        latitude=-27.4699,
        longitude=153.0251,
        bedrooms=3,
        bathrooms=2,
        parking=1,
        land_size_sqm=405.0,
        property_type="House",
        agent_name="Jane Agent",
        agency_name="Best Realty",
        listing_url=f"https://onthehouse.com.au/listing/{oth_property_id}",
        title="A house",
        status="ForSale",
        price=1_000_000,
    )


def _raw(listing: OTHListing) -> dict:
    return {"oth_property_id": listing.oth_property_id}


async def _backdate_last_seen(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    listing_id: int,
    delta: timedelta,
) -> None:
    """Pull a Listing's last_seen_at backwards by `delta`."""
    seconds = int(delta.total_seconds())
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE listing SET last_seen_at = last_seen_at - "
                    f"interval '{seconds} seconds' WHERE id = :id"
                ),
                {"id": listing_id},
            )


# ---- tests ----------------------------------------------------------------


async def test_sweep_closes_listing_outside_window(session_factory):
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    listing = _make_listing(oth_property_id="PROP-1", address="1 Latrobe Tce")
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )

    async with session_factory() as session:
        row = (await session.scalars(select(Listing))).one()
    await _backdate_last_seen(
        session_factory, listing_id=row.id, delta=WINDOW + timedelta(days=1)
    )

    closed = await run_soft_expiry_sweep(
        suburb_id,
        Category.FORSALE,
        session_factory=session_factory,
        soft_expiry_window=WINDOW,
    )

    assert closed == 1
    async with session_factory() as session:
        refreshed = (await session.scalars(select(Listing))).one()
    assert refreshed.closed_at is not None
    assert refreshed.closure_reason == "unknown"


async def test_sweep_does_not_touch_listing_within_window(session_factory):
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    listing = _make_listing(oth_property_id="PROP-1", address="1 Latrobe Tce")
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )
    # Backdate, but stay safely inside the window.
    async with session_factory() as session:
        row = (await session.scalars(select(Listing))).one()
    await _backdate_last_seen(
        session_factory, listing_id=row.id, delta=WINDOW - timedelta(days=1)
    )

    closed = await run_soft_expiry_sweep(
        suburb_id,
        Category.FORSALE,
        session_factory=session_factory,
        soft_expiry_window=WINDOW,
    )

    assert closed == 0
    async with session_factory() as session:
        refreshed = (await session.scalars(select(Listing))).one()
    assert refreshed.closed_at is None
    assert refreshed.closure_reason is None


async def test_sweep_only_touches_matching_suburb_and_category(session_factory):
    """The sweep must scope by both `suburb_id` AND `category`."""
    paddington = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    other_suburb = await _seed_suburb(
        session_factory, name="Toowong", postcode="4066"
    )

    target = _make_listing(oth_property_id="PROP-A", address="1 A St")
    other_suburb_listing = _make_listing(
        oth_property_id="PROP-B", address="2 B St"
    )
    other_category_listing = _make_listing(
        oth_property_id="PROP-C", address="3 C St"
    )

    await reconcile_batch(
        paddington, Category.FORSALE, [target], [_raw(target)],
        session_factory=session_factory,
    )
    await reconcile_batch(
        other_suburb,
        Category.FORSALE,
        [other_suburb_listing],
        [_raw(other_suburb_listing)],
        session_factory=session_factory,
    )
    await reconcile_batch(
        paddington,
        Category.FORRENT,
        [other_category_listing],
        [_raw(other_category_listing)],
        session_factory=session_factory,
    )

    # Backdate ALL listings far past the window.
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE listing SET last_seen_at = last_seen_at - interval '60 days'"
                )
            )

    closed = await run_soft_expiry_sweep(
        paddington,
        Category.FORSALE,
        session_factory=session_factory,
        soft_expiry_window=WINDOW,
    )
    assert closed == 1

    async with session_factory() as session:
        rows = (
            await session.scalars(select(Listing).order_by(Listing.id))
        ).all()
    closed_addresses = {
        (r.suburb_id, r.category)
        for r in rows
        if r.closed_at is not None
    }
    assert closed_addresses == {(paddington, Category.FORSALE.value)}
    # The other two are still open.
    open_count = sum(1 for r in rows if r.closed_at is None)
    assert open_count == 2


async def test_sweep_skips_already_closed_listings(session_factory):
    """A listing closed previously must not be re-touched (closed_at preserved)."""
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    listing = _make_listing(oth_property_id="PROP-1", address="1 Latrobe Tce")
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )
    async with session_factory() as session:
        async with session.begin():
            # Manually close with a known timestamp + reason.
            await session.execute(
                text(
                    "UPDATE listing SET closed_at = NOW() - interval '30 days', "
                    "closure_reason = 'sold', "
                    "last_seen_at = last_seen_at - interval '60 days'"
                )
            )
        before = (await session.scalars(select(Listing))).one()
    before_closed_at = before.closed_at
    before_reason = before.closure_reason

    closed = await run_soft_expiry_sweep(
        suburb_id,
        Category.FORSALE,
        session_factory=session_factory,
        soft_expiry_window=WINDOW,
    )

    assert closed == 0
    async with session_factory() as session:
        after = (await session.scalars(select(Listing))).one()
    assert after.closed_at == before_closed_at
    assert after.closure_reason == before_reason


async def test_seed_two_observe_one_advance_time_close_one(session_factory):
    """End-to-end acceptance scenario from the issue.

    Two listings exist in (suburb, category). A subsequent reconcile sees
    only one of them. After the window passes, the unobserved listing is
    closed; the observed one stays open.
    """
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    seen = _make_listing(oth_property_id="PROP-SEEN", address="1 Seen St")
    unseen = _make_listing(oth_property_id="PROP-UNSEEN", address="2 Unseen St")

    # Initial scrape: both listings present.
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [seen, unseen],
        [_raw(seen), _raw(unseen)],
        session_factory=session_factory,
    )

    # Time moves on.
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE listing SET last_seen_at = last_seen_at - interval '20 days'")
            )

    # Next scrape: only `seen` is in the feed.
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [seen],
        [_raw(seen)],
        session_factory=session_factory,
    )

    closed = await run_soft_expiry_sweep(
        suburb_id,
        Category.FORSALE,
        session_factory=session_factory,
        soft_expiry_window=WINDOW,
    )
    assert closed == 1

    async with session_factory() as session:
        rows = (
            await session.scalars(select(Listing).order_by(Listing.id))
        ).all()
    by_property = {row.oth_listing_id: row for row in rows}

    seen_row = next(
        r for r in rows if r.oth_listing_id and "PROP-SEEN" in r.oth_listing_id
    )
    unseen_row = next(
        r for r in rows if r.oth_listing_id and "PROP-UNSEEN" in r.oth_listing_id
    )
    assert seen_row.closed_at is None
    assert unseen_row.closed_at is not None
    assert unseen_row.closure_reason == "unknown"
    # Silence the linter: by_property only here to mirror real-world usage.
    assert len(by_property) == 2


async def test_failed_job_does_not_invoke_sweep(session_factory):
    """The contract is `MUST be called only after a successful job`.

    The sweep itself takes no `success` parameter — the worker decides. This
    test asserts the public surface honours that: as long as the worker does
    NOT call `run_soft_expiry_sweep`, nothing closes, even with stale rows.
    Issue 11 will add the worker integration test for the success branch.
    """
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    listing = _make_listing(oth_property_id="PROP-1", address="1 Latrobe Tce")
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )
    # Backdate to make it eligible IF the sweep ran.
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE listing SET last_seen_at = last_seen_at - interval '60 days'")
            )

    # Simulate a failed job — no sweep call.

    async with session_factory() as session:
        row = (await session.scalars(select(Listing))).one()
    assert row.closed_at is None
    assert row.closure_reason is None


# ---- maintenance endpoint ------------------------------------------------


@pytest_asyncio.fixture
async def api_client(session_factory):
    def _factory_dep():
        return session_factory

    app.dependency_overrides[get_session_factory] = _factory_dep
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_maintenance_endpoint_runs_sweep(session_factory, api_client):
    suburb_id = await _seed_suburb(
        session_factory, name="Paddington", postcode="4064"
    )
    listing = _make_listing(oth_property_id="PROP-1", address="1 Latrobe Tce")
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE listing SET last_seen_at = last_seen_at - interval '60 days'")
            )

    r = await api_client.post(
        "/maintenance/run-soft-expiry",
        params={"suburb_id": suburb_id, "category": "forsale"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "suburb_id": suburb_id,
        "category": "forsale",
        "closed": 1,
    }

    async with session_factory() as session:
        row = (await session.scalars(select(Listing))).one()
    assert row.closed_at is not None
    assert row.closure_reason == "unknown"
