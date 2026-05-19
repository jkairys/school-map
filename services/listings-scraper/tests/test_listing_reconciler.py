"""Integration tests for the listing reconciler.

Run against a real Postgres test container (see conftest). Each test asserts
externally observable DB state — never private structure of the reconciler.
"""
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.db.models import Listing, ListingSnapshot, Property, Suburb
from listings_scraper.listing_reconciler import reconcile_batch
from listings_scraper.oth_client.types import Category, OTHListing


# ---- helpers --------------------------------------------------------------


async def _seed_suburb(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Paddington",
    postcode: str = "4064",
    state: str = "QLD",
    oth_slug: str = "paddington-qld-4064",
) -> int:
    async with session_factory() as session:
        async with session.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state=state,
                oth_slug=oth_slug,
            )
            session.add(row)
            await session.flush()
            return row.id


def _make_listing(
    *,
    oth_property_id: str = "PROP-1",
    address: str = "1/12 Latrobe Tce, Paddington QLD",
    postcode: str = "4064",
    price: int | None = 1_200_000,
    title: str | None = "Pretty Queenslander",
    bedrooms: int | None = 3,
    bathrooms: int | None = 2,
    parking: int | None = 1,
    land_size_sqm: float | None = 405.0,
    property_type: str | None = "House",
    status: str | None = "ForSale",
    agent_name: str | None = "Jane Agent",
    agency_name: str | None = "Best Realty",
    listing_url: str | None = "https://onthehouse.com.au/listing/abc",
    latitude: float | None = -27.4699,
    longitude: float | None = 153.0251,
) -> OTHListing:
    return OTHListing(
        oth_property_id=oth_property_id,
        formatted_address=address,
        postcode=postcode,
        latitude=latitude,
        longitude=longitude,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        parking=parking,
        land_size_sqm=land_size_sqm,
        property_type=property_type,
        agent_name=agent_name,
        agency_name=agency_name,
        listing_url=listing_url,
        title=title,
        status=status,
        price=price,
    )


def _raw(listing: OTHListing) -> dict:
    """Stand-in for the raw OTH JSON. The reconciler stores it verbatim."""
    return {"oth_property_id": listing.oth_property_id, "title": listing.title}


# ---- tests ----------------------------------------------------------------


async def test_first_reconcile_creates_property_listing_and_snapshot(
    session_factory,
):
    suburb_id = await _seed_suburb(session_factory)
    listings = [
        _make_listing(oth_property_id="PROP-1", address="1/12 Latrobe Tce"),
        _make_listing(oth_property_id="PROP-2", address="9 Given Tce"),
        _make_listing(oth_property_id="PROP-3", address="44 Caxton St"),
    ]
    raws = [_raw(l) for l in listings]

    result = await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        listings,
        raws,
        session_factory=session_factory,
    )

    assert result.properties_upserted == 3
    assert result.listings_opened == 3
    assert result.snapshots_written == 3
    assert result.observations_unchanged == 0

    async with session_factory() as session:
        properties = (await session.scalars(select(Property))).all()
        listings_rows = (await session.scalars(select(Listing))).all()
        snapshots = (await session.scalars(select(ListingSnapshot))).all()

    assert len(properties) == 3
    assert len(listings_rows) == 3
    assert len(snapshots) == 3

    # changed_fields[0] is the __initial__ sentinel for the first snapshot.
    for snap in snapshots:
        assert snap.changed_fields[0] == "__initial__"
        assert snap.raw_payload["oth_property_id"].startswith("PROP-")


async def test_re_reconcile_same_batch_writes_no_new_snapshots(
    session_factory,
):
    suburb_id = await _seed_suburb(session_factory)
    listing = _make_listing(oth_property_id="PROP-1")
    batch = ([listing], [_raw(listing)])

    first = await reconcile_batch(
        suburb_id, Category.FORSALE, *batch, session_factory=session_factory
    )
    assert first.snapshots_written == 1

    # Capture last_seen_at after first run; the second run must move it forward.
    async with session_factory() as session:
        first_seen = (
            await session.execute(text("SELECT last_seen_at FROM listing"))
        ).scalar_one()

    # Force a measurable delta; Postgres CURRENT_TIMESTAMP is microsecond.
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE listing SET last_seen_at = last_seen_at - interval '1 hour'")
            )

    second = await reconcile_batch(
        suburb_id, Category.FORSALE, *batch, session_factory=session_factory
    )

    assert second.snapshots_written == 0
    assert second.observations_unchanged == 1
    assert second.properties_upserted == 0
    assert second.listings_opened == 0

    async with session_factory() as session:
        snapshots = (await session.scalars(select(ListingSnapshot))).all()
        new_seen = (
            await session.execute(text("SELECT last_seen_at FROM listing"))
        ).scalar_one()

    assert len(snapshots) == 1, "no new snapshot from an unchanged observation"
    assert new_seen > first_seen


async def test_single_field_change_writes_exactly_one_new_snapshot(
    session_factory,
):
    suburb_id = await _seed_suburb(session_factory)
    listing = _make_listing(oth_property_id="PROP-1", price=1_200_000)
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )

    # Only price changes — every other field is identical.
    dropped_price = listing.model_copy(update={"price": 1_150_000})
    result = await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [dropped_price],
        [_raw(dropped_price)],
        session_factory=session_factory,
    )

    assert result.snapshots_written == 1
    assert result.observations_unchanged == 0

    async with session_factory() as session:
        snapshots = (
            await session.scalars(
                select(ListingSnapshot).order_by(ListingSnapshot.id)
            )
        ).all()

    assert len(snapshots) == 2
    second = snapshots[1]
    assert second.changed_fields == ["price"]
    assert second.price == 1_150_000


async def test_relisting_attaches_second_listing_to_same_property(
    session_factory,
):
    suburb_id = await _seed_suburb(session_factory)
    first_listing = _make_listing(
        oth_property_id="PROP-1", listing_url="https://oth/x/1"
    )
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [first_listing],
        [_raw(first_listing)],
        session_factory=session_factory,
    )

    # Simulate the prior listing closing (the soft-expiry sweep would do this
    # in issue 09; here we close it directly so the reconciler must open a
    # fresh Listing for the same Property).
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text(
                    "UPDATE listing SET closed_at = NOW(), "
                    "closure_reason = 'unknown'"
                )
            )

    relisted = _make_listing(
        oth_property_id="PROP-1", listing_url="https://oth/x/2"
    )
    result = await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [relisted],
        [_raw(relisted)],
        session_factory=session_factory,
    )

    assert result.properties_upserted == 0
    assert result.listings_opened == 1
    assert result.snapshots_written == 1

    async with session_factory() as session:
        properties = (await session.scalars(select(Property))).all()
        listings_rows = (
            await session.scalars(select(Listing).order_by(Listing.id))
        ).all()

    assert len(properties) == 1
    assert len(listings_rows) == 2
    assert {l.property_id for l in listings_rows} == {properties[0].id}
    assert listings_rows[0].closed_at is not None
    assert listings_rows[1].closed_at is None
    assert listings_rows[1].oth_listing_id == "https://oth/x/2"


async def test_agent_change_updates_listing_no_snapshot(session_factory):
    suburb_id = await _seed_suburb(session_factory)
    initial = _make_listing(
        oth_property_id="PROP-1",
        agent_name="Jane Agent",
        agency_name="Best Realty",
    )
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [initial],
        [_raw(initial)],
        session_factory=session_factory,
    )

    moved_agent = initial.model_copy(
        update={"agent_name": "John Newagent", "agency_name": "Different Realty"}
    )
    result = await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [moved_agent],
        [_raw(moved_agent)],
        session_factory=session_factory,
    )

    assert result.snapshots_written == 0
    assert result.observations_unchanged == 1

    async with session_factory() as session:
        snapshots = (await session.scalars(select(ListingSnapshot))).all()
        listing_row = (await session.scalars(select(Listing))).one()

    assert len(snapshots) == 1, "agent/agency moves are not material"
    assert listing_row.agent_name == "John Newagent"
    assert listing_row.agency_name == "Different Realty"


async def test_postgis_location_column_persists_a_point(session_factory):
    """Acceptance criterion: PostGIS column accepts a Point."""
    suburb_id = await _seed_suburb(session_factory)
    listing = _make_listing(
        oth_property_id="PROP-1", latitude=-27.4699, longitude=153.0251
    )
    await reconcile_batch(
        suburb_id,
        Category.FORSALE,
        [listing],
        [_raw(listing)],
        session_factory=session_factory,
    )

    async with session_factory() as session:
        # Round-trip via PostGIS so we know the value is a real point, not text.
        row = (
            await session.execute(
                text(
                    "SELECT ST_X(location::geometry) AS lon, "
                    "ST_Y(location::geometry) AS lat FROM property"
                )
            )
        ).one()

    assert row.lat == pytest.approx(-27.4699, abs=1e-6)
    assert row.lon == pytest.approx(153.0251, abs=1e-6)
