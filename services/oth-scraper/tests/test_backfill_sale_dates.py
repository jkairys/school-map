"""Integration tests for the backfill_sale_dates script.

Runs against the shared Postgres test container (see conftest). Each test
seeds minimal DB state, calls the backfill function directly, and asserts
externally observable DB state — no private internals touched.
"""
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.db.models import Listing, ListingSnapshot, Property, Suburb
from oth_scraper.scripts.backfill_sale_dates import backfill_sale_dates


# ---- helpers -----------------------------------------------------------------


async def _seed_suburb(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Paddington",
    postcode: str = "4064",
    state: str = "QLD",
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state=state,
                oth_slug=f"{name.lower()}-{state.lower()}-{postcode}",
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_property(
    session_factory: async_sessionmaker[AsyncSession],
    suburb_id: int,
    *,
    address: str = "1 Test St, Paddington QLD",
    postcode: str = "4064",
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = Property(
                oth_property_id=f"OTH-{address[:8]}",
                formatted_address=address,
                postcode=postcode,
                suburb_id=suburb_id,
                location=None,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_listing(
    session_factory: async_sessionmaker[AsyncSession],
    property_id: int,
    suburb_id: int,
    *,
    category: str = "recentlysold",
    sale_date: date | None = None,
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = Listing(
                property_id=property_id,
                suburb_id=suburb_id,
                category=category,
                sale_date=sale_date,
            )
            session.add(row)
            await session.flush()
            return row.id


async def _seed_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    listing_id: int,
    raw_payload: dict,
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = ListingSnapshot(
                listing_id=listing_id,
                raw_payload=raw_payload,
                changed_fields=["__initial__"],
            )
            session.add(row)
            await session.flush()
            return row.id


# ---- tests -------------------------------------------------------------------


async def test_backfill_populates_null_sale_date(session_factory):
    """A recentlysold listing with sale_date=NULL gets populated from its snapshot."""
    suburb_id = await _seed_suburb(session_factory)
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory, prop_id, suburb_id, category="recentlysold", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_id,
        raw_payload={"lastSale": {"eventDate": "2026-04-28"}},
    )

    counts = await backfill_sale_dates(session_factory)

    assert counts.scanned == 1
    assert counts.populated == 1
    assert counts.no_payload == 0
    assert counts.no_date_in_payload == 0

    async with session_factory() as session:
        row = await session.get(Listing, listing_id)

    assert row is not None
    assert row.sale_date == date(2026, 4, 28)


async def test_backfill_skips_listing_with_sale_date_already_set(session_factory):
    """A recentlysold listing whose sale_date is already populated is untouched."""
    suburb_id = await _seed_suburb(session_factory)
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory,
        prop_id,
        suburb_id,
        category="recentlysold",
        sale_date=date(2025, 12, 1),
    )
    await _seed_snapshot(
        session_factory,
        listing_id,
        raw_payload={"lastSale": {"eventDate": "2026-04-28"}},
    )

    counts = await backfill_sale_dates(session_factory)

    # Already populated — WHERE clause excludes it entirely.
    assert counts.scanned == 0
    assert counts.populated == 0

    async with session_factory() as session:
        row = await session.get(Listing, listing_id)

    assert row is not None
    # Unchanged — stays at the pre-seeded value.
    assert row.sale_date == date(2025, 12, 1)


async def test_backfill_ignores_forsale_category(session_factory):
    """forsale listings with sale_date=NULL are never touched."""
    suburb_id = await _seed_suburb(session_factory)
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory, prop_id, suburb_id, category="forsale", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_id,
        # Include a lastSale block — should still be ignored because category is wrong.
        raw_payload={"lastSale": {"eventDate": "2026-04-28"}},
    )

    counts = await backfill_sale_dates(session_factory)

    assert counts.scanned == 0  # forsale excluded by WHERE clause
    assert counts.populated == 0

    async with session_factory() as session:
        row = await session.get(Listing, listing_id)

    assert row is not None
    assert row.sale_date is None  # untouched


async def test_backfill_full_scenario(session_factory):
    """Combined scenario: three listings, three different outcomes.

    - Listing A: recentlysold, sale_date=NULL, payload has date  → populated
    - Listing B: recentlysold, sale_date already set              → skipped
    - Listing C: forsale, sale_date=NULL                          → ignored
    """
    suburb_id = await _seed_suburb(session_factory)

    # Listing A — needs backfill
    prop_a = await _seed_property(session_factory, suburb_id, address="1 A St")
    listing_a = await _seed_listing(
        session_factory, prop_a, suburb_id, category="recentlysold", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_a,
        raw_payload={"lastSale": {"eventDate": "2026-04-28"}},
    )

    # Listing B — already has sale_date; must not be changed
    prop_b = await _seed_property(session_factory, suburb_id, address="2 B St")
    listing_b = await _seed_listing(
        session_factory,
        prop_b,
        suburb_id,
        category="recentlysold",
        sale_date=date(2025, 6, 15),
    )
    await _seed_snapshot(
        session_factory,
        listing_b,
        raw_payload={"lastSale": {"eventDate": "2025-06-15"}},
    )

    # Listing C — forsale; should never be touched
    prop_c = await _seed_property(session_factory, suburb_id, address="3 C St")
    listing_c = await _seed_listing(
        session_factory, prop_c, suburb_id, category="forsale", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_c,
        raw_payload={"listing": {"displayPrice": "Offers over $950,000"}},
    )

    counts = await backfill_sale_dates(session_factory)

    # Only listing A is in scope (recentlysold + sale_date IS NULL).
    assert counts.scanned == 1
    assert counts.populated == 1
    assert counts.no_payload == 0
    assert counts.no_date_in_payload == 0

    async with session_factory() as session:
        row_a = await session.get(Listing, listing_a)
        row_b = await session.get(Listing, listing_b)
        row_c = await session.get(Listing, listing_c)

    assert row_a is not None and row_a.sale_date == date(2026, 4, 28)
    assert row_b is not None and row_b.sale_date == date(2025, 6, 15)  # unchanged
    assert row_c is not None and row_c.sale_date is None              # untouched


async def test_backfill_no_date_in_payload(session_factory):
    """Snapshot exists but payload has no lastSale.eventDate — increments no_date_in_payload."""
    suburb_id = await _seed_suburb(session_factory)
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory, prop_id, suburb_id, category="recentlysold", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_id,
        raw_payload={"lastSale": {}},  # missing eventDate
    )

    counts = await backfill_sale_dates(session_factory)

    assert counts.scanned == 1
    assert counts.populated == 0
    assert counts.no_date_in_payload == 1

    async with session_factory() as session:
        row = await session.get(Listing, listing_id)

    assert row is not None
    assert row.sale_date is None  # still null — nothing to write


async def test_backfill_is_idempotent(session_factory):
    """Running the backfill twice yields the same result without double-writing."""
    suburb_id = await _seed_suburb(session_factory)
    prop_id = await _seed_property(session_factory, suburb_id)
    listing_id = await _seed_listing(
        session_factory, prop_id, suburb_id, category="recentlysold", sale_date=None
    )
    await _seed_snapshot(
        session_factory,
        listing_id,
        raw_payload={"lastSale": {"eventDate": "2026-04-28"}},
    )

    first = await backfill_sale_dates(session_factory)
    assert first.populated == 1

    # Second run: sale_date is now set, so the WHERE clause excludes this row.
    second = await backfill_sale_dates(session_factory)
    assert second.scanned == 0
    assert second.populated == 0

    async with session_factory() as session:
        row = await session.get(Listing, listing_id)

    assert row is not None
    assert row.sale_date == date(2026, 4, 28)
