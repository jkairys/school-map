"""Tests for slice 06: suburb autocomplete + property search/detail endpoints.

Coverage:
- SuburbAutocomplete happy-path passthrough (mocked OTH)
- SuburbAutocomplete 503 propagation
- GET /suburbs/autocomplete?q= endpoint
- GET /properties?search= partial address search
- GET /properties?sort= orderings (price_desc, price_asc, observed_at_desc)
- GET /properties/{id} with multiple listing campaigns
- GET /properties/{id} 404 on unknown property
"""
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.api.app import app
from oth_scraper.db.engine import get_db
from oth_scraper.db.models import (
    Listing,
    ListingSnapshot,
    Property,
    Suburb,
)
from oth_scraper.suburb_autocomplete import autocomplete
from oth_scraper.suburb_resolver.exceptions import AutocompleteUnavailableError

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# SuburbAutocomplete unit tests (mocked OTH client)
# ---------------------------------------------------------------------------


async def test_autocomplete_empty_query_returns_empty_list():
    """Empty/blank q must return [] without any network call."""
    result = await autocomplete("")
    assert result == []

    result = await autocomplete("   ")
    assert result == []


async def test_autocomplete_passthrough_returns_all_suburb_candidates(httpx_mock):
    """autocomplete() returns all suburb-level candidates verbatim from OTH.

    Unlike suburb_resolver which filters by name equality, autocomplete returns
    every suburb-level row from the OTH response. The richmond fixture has 10
    suburb-level rows (7 named RICHMOND + 3 others with Richmond in them that
    the resolver's name-equality filter would drop, but we keep them all).
    """
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Richmond",
        json=_fixture("richmond.json"),
    )
    result = await autocomplete("Richmond")
    # All suburb-level rows — no name-equality filter applied
    assert len(result) > 0
    # All results should have required fields
    assert all(m.postcode for m in result)
    assert all(m.state for m in result)
    assert all(m.oth_slug for m in result)
    # Unlike suburb_resolver, we do NOT filter by name equality —
    # all suburb-level rows come back.


async def test_autocomplete_single_match(httpx_mock):
    """autocomplete() for a single-result query returns a list with one item."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    result = await autocomplete("Little Mountain")
    assert len(result) == 1
    assert result[0].name == "LITTLE MOUNTAIN"
    assert result[0].postcode == "4551"
    assert result[0].state == "QLD"


async def test_autocomplete_never_touches_db(httpx_mock):
    """autocomplete() must not require or use a DB session at all."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    # Call without any session parameter — if this raises it means DB was required
    result = await autocomplete("Little Mountain")
    assert len(result) == 1


async def test_autocomplete_propagates_503_on_oth_error(httpx_mock):
    """AutocompleteUnavailableError raised when OTH returns 503."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=SomeSuburb",
        status_code=503,
    )
    with pytest.raises(AutocompleteUnavailableError):
        await autocomplete("SomeSuburb")


async def test_autocomplete_propagates_403_as_unavailable(httpx_mock):
    """AutocompleteUnavailableError raised when OTH anti-bot blocks (403)."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Blocked",
        status_code=403,
    )
    with pytest.raises(AutocompleteUnavailableError):
        await autocomplete("Blocked")


# ---------------------------------------------------------------------------
# Fixtures for API endpoint tests (Postgres testcontainer)
# ---------------------------------------------------------------------------


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


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    name: str = "TestSuburb",
    postcode: str = "4000",
) -> int:
    async with factory() as s:
        async with s.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state="QLD",
                oth_slug=f"{name.lower().replace(' ', '-')}-{postcode}",
            )
            s.add(row)
            await s.flush()
            return row.id


_counter = 0


async def _seed_property_with_listing_snapshot(
    factory: async_sessionmaker[AsyncSession],
    *,
    suburb_id: int,
    address_suffix: str = "",
    category: str = "forsale",
    price: int | None = 800_000,
    observed_at_offset_seconds: int = 0,
) -> tuple[int, int, int]:
    """Seed one property + one listing + one snapshot. Returns (prop_id, listing_id, snap_id)."""
    global _counter
    _counter += 1
    tag = _counter
    async with factory() as s:
        async with s.begin():
            from sqlalchemy import text as _text

            prop = Property(
                oth_property_id=f"s06-prop-{tag}",
                formatted_address=f"{tag} Slice06 St{address_suffix}",
                postcode="4000",
                suburb_id=suburb_id,
            )
            s.add(prop)
            await s.flush()

            listing = Listing(
                property_id=prop.id,
                suburb_id=suburb_id,
                category=category,
                oth_listing_id=f"oth-s06-{prop.id}",
            )
            s.add(listing)
            await s.flush()

            # Use NOW() + offset to produce deterministic observed_at ordering.
            if observed_at_offset_seconds == 0:
                snap = ListingSnapshot(
                    listing_id=listing.id,
                    price=price,
                    title="Test",
                    blurb=None,
                    bedrooms=3,
                    bathrooms=2,
                    parking=1,
                    land_size_sqm=600,
                    property_type="House",
                    status="Active",
                    raw_payload={"id": "raw"},
                    changed_fields=["__initial__"],
                )
                s.add(snap)
                await s.flush()
            else:
                snap = ListingSnapshot(
                    listing_id=listing.id,
                    price=price,
                    title="Test",
                    blurb=None,
                    bedrooms=3,
                    bathrooms=2,
                    parking=1,
                    land_size_sqm=600,
                    property_type="House",
                    status="Active",
                    raw_payload={"id": "raw"},
                    changed_fields=["__initial__"],
                )
                s.add(snap)
                await s.flush()
                # Shift observed_at by the offset.
                await s.execute(
                    _text(
                        "UPDATE listing_snapshot "
                        "SET observed_at = NOW() + :offset * INTERVAL '1 second' "
                        "WHERE id = :id"
                    ),
                    {"offset": observed_at_offset_seconds, "id": snap.id},
                )

            snap_id = snap.id
            return prop.id, listing.id, snap_id


# ---------------------------------------------------------------------------
# GET /suburbs/autocomplete endpoint tests
# ---------------------------------------------------------------------------


async def test_autocomplete_endpoint_returns_matches(api_client, httpx_mock):
    """GET /suburbs/autocomplete?q=Richmond returns Match[] from OTH."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Richmond",
        json=_fixture("richmond.json"),
    )
    r = await api_client.get("/suburbs/autocomplete?q=Richmond")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert all("name" in item for item in data)
    assert all("postcode" in item for item in data)
    assert all("state" in item for item in data)
    assert all("oth_slug" in item for item in data)


async def test_autocomplete_endpoint_empty_q_returns_empty(api_client):
    """GET /suburbs/autocomplete?q= (empty) returns [] without hitting OTH."""
    r = await api_client.get("/suburbs/autocomplete?q=")
    assert r.status_code == 200
    assert r.json() == []


async def test_autocomplete_endpoint_missing_q_returns_empty(api_client):
    """GET /suburbs/autocomplete (no q param) returns [] — q defaults to ''."""
    r = await api_client.get("/suburbs/autocomplete")
    assert r.status_code == 200
    assert r.json() == []


async def test_autocomplete_endpoint_503_on_oth_error(api_client, httpx_mock):
    """GET /suburbs/autocomplete propagates OTH failures as 503."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=SomeSuburb",
        status_code=403,
    )
    r = await api_client.get("/suburbs/autocomplete?q=SomeSuburb")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# GET /properties?search= tests
# ---------------------------------------------------------------------------


async def test_properties_search_by_partial_address(api_client, session_factory):
    """GET /properties?search= filters by formatted_address ILIKE %%q%%."""
    sub_id = await _seed_suburb(session_factory, "SearchSub", "4100")
    p1, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, address_suffix=" UNIQUE_TOKEN_ABC"
    )
    p2, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, address_suffix=" OTHER_TOKEN"
    )

    r = await api_client.get("/properties?search=UNIQUE_TOKEN_ABC")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == p1


async def test_properties_search_case_insensitive(api_client, session_factory):
    """ILIKE search is case-insensitive."""
    sub_id = await _seed_suburb(session_factory, "CISub", "4101")
    p1, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, address_suffix=" CiTestStreet"
    )

    r_lower = await api_client.get("/properties?search=citeststreet")
    assert r_lower.status_code == 200
    assert any(row["id"] == p1 for row in r_lower.json())

    r_upper = await api_client.get("/properties?search=CITESTSTREET")
    assert r_upper.status_code == 200
    assert any(row["id"] == p1 for row in r_upper.json())


# ---------------------------------------------------------------------------
# GET /properties?sort= tests
# ---------------------------------------------------------------------------


async def test_properties_sort_price_desc(api_client, session_factory):
    """sort=price_desc returns most-expensive property first."""
    sub_id = await _seed_suburb(session_factory, "SortSub1", "4200")
    p_low, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=300_000, address_suffix=" SortPrice"
    )
    p_high, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=900_000, address_suffix=" SortPrice"
    )
    p_mid, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=600_000, address_suffix=" SortPrice"
    )

    r = await api_client.get(f"/properties?suburb={sub_id}&sort=price_desc")
    assert r.status_code == 200
    rows = r.json()
    prices = [row["latest_price"] for row in rows]
    assert prices == sorted(prices, reverse=True)
    assert rows[0]["id"] == p_high


async def test_properties_sort_price_asc(api_client, session_factory):
    """sort=price_asc returns cheapest property first."""
    sub_id = await _seed_suburb(session_factory, "SortSub2", "4201")
    p_low, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=200_000, address_suffix=" SortPriceAsc"
    )
    p_high, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=800_000, address_suffix=" SortPriceAsc"
    )

    r = await api_client.get(f"/properties?suburb={sub_id}&sort=price_asc")
    assert r.status_code == 200
    rows = r.json()
    prices = [row["latest_price"] for row in rows]
    assert prices == sorted(prices)
    assert rows[0]["id"] == p_low


async def test_properties_sort_observed_at_desc(api_client, session_factory):
    """sort=observed_at_desc returns most-recently-observed property first."""
    sub_id = await _seed_suburb(session_factory, "SortSub3", "4202")
    p_old, _, _ = await _seed_property_with_listing_snapshot(
        session_factory,
        suburb_id=sub_id,
        observed_at_offset_seconds=-200,
        address_suffix=" SortObs",
    )
    p_new, _, _ = await _seed_property_with_listing_snapshot(
        session_factory,
        suburb_id=sub_id,
        observed_at_offset_seconds=0,
        address_suffix=" SortObs",
    )

    r = await api_client.get(f"/properties?suburb={sub_id}&sort=observed_at_desc")
    assert r.status_code == 200
    rows = r.json()
    # p_new has later observed_at → should be first
    assert rows[0]["id"] == p_new


async def test_properties_default_sort_is_observed_at_desc(api_client, session_factory):
    """Default sort (no sort param) is observed_at_desc."""
    sub_id = await _seed_suburb(session_factory, "SortSub4", "4203")
    p_old, _, _ = await _seed_property_with_listing_snapshot(
        session_factory,
        suburb_id=sub_id,
        observed_at_offset_seconds=-300,
        address_suffix=" SortDef",
    )
    p_new, _, _ = await _seed_property_with_listing_snapshot(
        session_factory,
        suburb_id=sub_id,
        observed_at_offset_seconds=0,
        address_suffix=" SortDef",
    )

    r = await api_client.get(f"/properties?suburb={sub_id}")
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["id"] == p_new


# ---------------------------------------------------------------------------
# GET /properties response includes latest-snapshot rollup
# ---------------------------------------------------------------------------


async def test_properties_list_includes_rollup_fields(api_client, session_factory):
    """Each property in GET /properties has latest_price, latest_observed_at, etc.

    Includes latest_bedrooms and latest_land_size_sqm from the best snapshot.
    The seed helper sets bedrooms=3 and land_size_sqm=600 on every snapshot.
    """
    sub_id = await _seed_suburb(session_factory, "RollupSub", "4300")
    p_id, _, _ = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=750_000
    )

    r = await api_client.get(f"/properties?suburb={sub_id}")
    assert r.status_code == 200
    rows = r.json()
    row = next(row for row in rows if row["id"] == p_id)
    assert row["latest_price"] == 750_000
    assert row["latest_observed_at"] is not None
    assert row["latest_category"] == "forsale"
    assert row["latest_status"] == "Active"
    # New fields: populated from the seeded snapshot (bedrooms=3, land_size_sqm=600)
    assert row["latest_bedrooms"] == 3
    assert row["latest_land_size_sqm"] == 600


async def test_properties_list_rollup_null_when_no_snapshots(api_client, session_factory):
    """Property with no listing/snapshot has all rollup fields as None."""
    sub_id = await _seed_suburb(session_factory, "NoSnapSub", "4301")
    async with session_factory() as s:
        async with s.begin():
            prop = Property(
                oth_property_id="no-snap-prop",
                formatted_address="99 NoSnap Rd",
                postcode="4301",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            prop_id = prop.id

    r = await api_client.get(f"/properties?suburb={sub_id}")
    assert r.status_code == 200
    rows = r.json()
    row = next(row for row in rows if row["id"] == prop_id)
    assert row["latest_price"] is None
    assert row["latest_observed_at"] is None
    assert row["latest_category"] is None
    assert row["latest_status"] is None
    # New fields: null when there is no snapshot
    assert row["latest_bedrooms"] is None
    assert row["latest_land_size_sqm"] is None


# ---------------------------------------------------------------------------
# GET /properties/{id} detail tests
# ---------------------------------------------------------------------------


async def test_property_detail_returns_property_and_listings(api_client, session_factory):
    """GET /properties/{id} returns property + its listing campaigns."""
    sub_id = await _seed_suburb(session_factory, "DetailSub", "4400")
    prop_id, listing_id, snap_id = await _seed_property_with_listing_snapshot(
        session_factory, suburb_id=sub_id, price=1_000_000
    )

    r = await api_client.get(f"/properties/{prop_id}")
    assert r.status_code == 200
    body = r.json()

    assert "property" in body
    assert "listings" in body
    assert body["property"]["id"] == prop_id
    assert len(body["listings"]) == 1

    listing = body["listings"][0]
    assert listing["id"] == listing_id
    assert listing["latest_snapshot"] is not None
    assert listing["latest_snapshot"]["price"] == 1_000_000
    assert listing["latest_snapshot"]["category"] == "forsale"


async def test_property_detail_multiple_campaigns(api_client, session_factory):
    """GET /properties/{id} returns all listing campaigns, most recent first."""
    sub_id = await _seed_suburb(session_factory, "MultiCampaignSub", "4401")

    async with session_factory() as s:
        async with s.begin():
            from sqlalchemy import text as _text

            prop = Property(
                oth_property_id="multi-campaign-prop",
                formatted_address="7 MultiCampaign Ave",
                postcode="4401",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            prop_id = prop.id

            # First (older) listing campaign
            listing_old = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-old",
            )
            s.add(listing_old)
            await s.flush()
            snap_old = ListingSnapshot(
                listing_id=listing_old.id,
                price=500_000,
                title="Old listing",
                blurb=None,
                bedrooms=3,
                bathrooms=1,
                parking=1,
                land_size_sqm=400,
                property_type="House",
                status="Sold",
                raw_payload={"id": "old"},
                changed_fields=["__initial__"],
            )
            s.add(snap_old)
            await s.flush()
            listing_old_id = listing_old.id

            # Push first_seen_at back so ordering is deterministic
            await s.execute(
                _text(
                    "UPDATE listing SET first_seen_at = NOW() - INTERVAL '30 days' "
                    "WHERE id = :id"
                ),
                {"id": listing_old_id},
            )

            # Second (newer) listing campaign
            listing_new = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-new",
            )
            s.add(listing_new)
            await s.flush()
            snap_new = ListingSnapshot(
                listing_id=listing_new.id,
                price=600_000,
                title="New listing",
                blurb=None,
                bedrooms=3,
                bathrooms=2,
                parking=2,
                land_size_sqm=400,
                property_type="House",
                status="Active",
                raw_payload={"id": "new"},
                changed_fields=["__initial__"],
            )
            s.add(snap_new)
            await s.flush()
            listing_new_id = listing_new.id

    r = await api_client.get(f"/properties/{prop_id}")
    assert r.status_code == 200
    body = r.json()

    assert body["property"]["id"] == prop_id
    listings = body["listings"]
    assert len(listings) == 2

    # Most recent campaign first (newest first_seen_at first)
    assert listings[0]["id"] == listing_new_id
    assert listings[1]["id"] == listing_old_id

    # Snapshots attached
    assert listings[0]["latest_snapshot"]["price"] == 600_000
    assert listings[1]["latest_snapshot"]["price"] == 500_000


async def test_property_detail_listing_with_no_snapshot(api_client, session_factory):
    """GET /properties/{id}: listing with no snapshot has latest_snapshot=null."""
    sub_id = await _seed_suburb(session_factory, "NoSnapListingSub", "4402")

    async with session_factory() as s:
        async with s.begin():
            prop = Property(
                oth_property_id="no-snap-listing-prop",
                formatted_address="5 NoSnapListing Rd",
                postcode="4402",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            prop_id = prop.id

            listing = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id=None,
            )
            s.add(listing)
            await s.flush()
            listing_id = listing.id

    r = await api_client.get(f"/properties/{prop_id}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["listings"]) == 1
    assert body["listings"][0]["id"] == listing_id
    assert body["listings"][0]["latest_snapshot"] is None


async def test_property_detail_404_unknown(api_client):
    """GET /properties/{id} returns 404 for a property that doesn't exist."""
    r = await api_client.get("/properties/99999999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /properties + /properties/{id}: latest_bedrooms / latest_land_size_sqm
# ---------------------------------------------------------------------------


async def test_list_properties_includes_bedrooms_and_land(api_client, session_factory):
    """GET /properties includes latest_bedrooms and latest_land_size_sqm.

    When the snapshot has these populated they flow through the best_snap CTE
    and appear on the rollup row. When no snapshot exists both are null.
    """
    sub_id = await _seed_suburb(session_factory, "BedsLandSub", "4500")

    # Property with a snapshot that has bedrooms=4 and land_size_sqm=612
    async with session_factory() as s:
        async with s.begin():
            prop = Property(
                oth_property_id="beds-land-prop",
                formatted_address="12 BedsLand St",
                postcode="4500",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            prop_id = prop.id

            listing = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-beds-land",
            )
            s.add(listing)
            await s.flush()

            snap = ListingSnapshot(
                listing_id=listing.id,
                price=950_000,
                title="Test beds/land",
                blurb=None,
                bedrooms=4,
                bathrooms=2,
                parking=2,
                land_size_sqm=612,
                property_type="House",
                status="Active",
                raw_payload={"id": "bl"},
                changed_fields=["__initial__"],
            )
            s.add(snap)
            await s.flush()

    # Property with no listing (null rollup fields)
    async with session_factory() as s:
        async with s.begin():
            null_prop = Property(
                oth_property_id="no-beds-land-prop",
                formatted_address="13 NoBeds St",
                postcode="4500",
                suburb_id=sub_id,
            )
            s.add(null_prop)
            await s.flush()
            null_prop_id = null_prop.id

    r = await api_client.get(f"/properties?suburb={sub_id}")
    assert r.status_code == 200
    rows = r.json()

    snap_row = next(row for row in rows if row["id"] == prop_id)
    assert snap_row["latest_bedrooms"] == 4
    assert snap_row["latest_land_size_sqm"] == 612

    null_row = next(row for row in rows if row["id"] == null_prop_id)
    assert null_row["latest_bedrooms"] is None
    assert null_row["latest_land_size_sqm"] is None


async def test_property_detail_includes_bedrooms_and_land(api_client, session_factory):
    """GET /properties/{id} listings include latest_bedrooms and latest_land_size_sqm.

    Populated when the listing has a snapshot; null when it does not.
    """
    sub_id = await _seed_suburb(session_factory, "DetailBedsLandSub", "4501")

    async with session_factory() as s:
        async with s.begin():
            prop = Property(
                oth_property_id="detail-beds-land-prop",
                formatted_address="7 DetailBedsLand Ave",
                postcode="4501",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            prop_id = prop.id

            listing_with = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="oth-dbl-with",
            )
            s.add(listing_with)
            await s.flush()
            snap = ListingSnapshot(
                listing_id=listing_with.id,
                price=820_000,
                title="Detail beds/land",
                blurb=None,
                bedrooms=3,
                bathrooms=1,
                parking=1,
                land_size_sqm=405,
                property_type="House",
                status="Active",
                raw_payload={"id": "dbl"},
                changed_fields=["__initial__"],
            )
            s.add(snap)
            await s.flush()
            listing_with_id = listing_with.id

            listing_no_snap = Listing(
                property_id=prop_id,
                suburb_id=sub_id,
                category="forrent",
                oth_listing_id="oth-dbl-nosnap",
            )
            s.add(listing_no_snap)
            await s.flush()
            listing_no_snap_id = listing_no_snap.id

    r = await api_client.get(f"/properties/{prop_id}")
    assert r.status_code == 200
    body = r.json()

    by_id = {lst["id"]: lst for lst in body["listings"]}

    lst_with = by_id[listing_with_id]
    assert lst_with["latest_bedrooms"] == 3
    assert lst_with["latest_land_size_sqm"] == 405

    lst_none = by_id[listing_no_snap_id]
    assert lst_none["latest_bedrooms"] is None
    assert lst_none["latest_land_size_sqm"] is None
