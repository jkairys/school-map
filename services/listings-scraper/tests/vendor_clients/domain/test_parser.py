"""Tests for the Domain vendor client parser.

Uses the captured spike fixture at
tests/fixtures/domain/next_data_search_paddington.json
as the primary data source — the fixture was captured from a live Domain
search for Paddington QLD 4064 (for sale) and contains 20 listings.
"""

import json
import pathlib
from datetime import datetime, timezone

import pytest

from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import PriceKind, VendorListing
from listings_scraper.vendor_clients.domain.next_data import extract_next_data
from listings_scraper.vendor_clients.domain.parser import parse_next_data_listings
from listings_scraper.vendor_clients.oth.types import Category

FIXTURE_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "fixtures"
    / "domain"
    / "next_data_search_paddington.json"
)

_OBSERVED_AT = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def paddington_next_data() -> dict:
    """Load the captured Paddington QLD forsale fixture."""
    with open(FIXTURE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Parser round-trip: fixture → VendorListing list
# ---------------------------------------------------------------------------


def test_parse_fixture_yields_enough_listings(paddington_next_data: dict) -> None:
    """Parser must yield at least 15 VendorListing objects from the 20-listing fixture."""
    listings, raw_payloads = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    assert len(listings) >= 15, (
        f"Expected ≥15 listings from fixture, got {len(listings)}"
    )
    assert len(raw_payloads) == len(listings), (
        "raw_payloads must be parallel to listings"
    )


def test_parse_fixture_all_source_domain(paddington_next_data: dict) -> None:
    """Every listing from a Domain parse must have source=Vendor.DOMAIN."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        assert listing.source is Vendor.DOMAIN, f"listing {listing.external_listing_id} has wrong source"


def test_parse_fixture_required_fields_populated(paddington_next_data: dict) -> None:
    """Every listing must have a non-empty formatted_address, external_listing_id,
    and at least some coordinate data."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        assert listing.formatted_address, (
            f"listing {listing.external_listing_id} has empty formatted_address"
        )
        assert listing.external_listing_id, (
            f"listing has empty external_listing_id"
        )
        # Domain search results always include lat/lng
        assert listing.latitude is not None, (
            f"listing {listing.external_listing_id} has no latitude"
        )
        assert listing.longitude is not None, (
            f"listing {listing.external_listing_id} has no longitude"
        )


def test_parse_fixture_beds_baths_for_houses(paddington_next_data: dict) -> None:
    """House listings in the fixture should have beds and baths populated."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    houses = [l for l in listings if l.property_type and "house" in l.property_type.lower()]
    # There are houses in the Paddington forsale fixture — assert at least one
    # has beds/baths populated
    has_beds = sum(1 for l in houses if l.bedrooms is not None)
    assert has_beds >= 1, "Expected at least one house listing with bedrooms populated"


def test_parse_fixture_listing_url_absolute(paddington_next_data: dict) -> None:
    """listing_url must be an absolute URL starting with https://www.domain.com.au."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        if listing.listing_url is not None:
            assert listing.listing_url.startswith("https://www.domain.com.au/"), (
                f"listing_url not absolute: {listing.listing_url}"
            )


def test_parse_fixture_observed_at_preserved(paddington_next_data: dict) -> None:
    """All listings must carry the observed_at timestamp passed to the parser."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        assert listing.observed_at == _OBSERVED_AT


def test_parse_fixture_under_offer_listings_have_status(paddington_next_data: dict) -> None:
    """Listings with 'Under offer' tag must have status='under_offer'."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    # The fixture has listings with tag "Under offer" — find them by external ID
    # (known from fixture inspection: 2020667730, 2020719627, 2020762483, 2020778104)
    under_offer_ids = {"2020667730", "2020719627", "2020762483", "2020778104"}
    for listing in listings:
        if listing.external_listing_id in under_offer_ids:
            assert listing.status == "under_offer", (
                f"listing {listing.external_listing_id} should have status=under_offer"
            )


def test_parse_fixture_new_tag_does_not_set_status(paddington_next_data: dict) -> None:
    """Listings with 'New' tag (noise) must NOT have status='new' — status should be None."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    # 2020568511 has tag "New" — it should not be marked as new status
    new_tag_ids = {"2020568511", "2020841855", "2020849154"}
    for listing in listings:
        if listing.external_listing_id in new_tag_ids:
            assert listing.status != "new", (
                f"listing {listing.external_listing_id} should not have status=new (tag noise)"
            )
            # For New-tagged listings without Under offer / Sold, status should be None
            assert listing.status is None, (
                f"listing {listing.external_listing_id} status should be None, got {listing.status}"
            )


def test_parse_fixture_external_ids_stable(paddington_next_data: dict) -> None:
    """external_listing_id == external_property_id (Domain design: no separate property ID)."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        assert listing.external_listing_id == listing.external_property_id, (
            f"Domain: external_listing_id should equal external_property_id "
            f"for listing {listing.external_listing_id}"
        )


def test_parse_fixture_postcode_and_state(paddington_next_data: dict) -> None:
    """All Paddington listings should have postcode=4064 and state=QLD."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    for listing in listings:
        assert listing.postcode == "4064", (
            f"listing {listing.external_listing_id} has unexpected postcode: {listing.postcode}"
        )
        assert listing.state == "QLD", (
            f"listing {listing.external_listing_id} has unexpected state: {listing.state}"
        )


# ---------------------------------------------------------------------------
# next_data.py extraction
# ---------------------------------------------------------------------------


def test_extract_next_data_from_html() -> None:
    """extract_next_data must find and parse the __NEXT_DATA__ script tag."""
    fixture_json = FIXTURE_PATH.read_text()
    html = f'<html><head><script id="__NEXT_DATA__" type="application/json">{fixture_json}</script></head></html>'
    result = extract_next_data(html)
    assert isinstance(result, dict)
    assert "props" in result


def test_extract_next_data_missing_raises() -> None:
    """extract_next_data must raise ParseError when the tag is absent."""
    from listings_scraper.vendor_clients.domain.exceptions import ParseError
    with pytest.raises(ParseError):
        extract_next_data("<html><body>No next data here</body></html>")


def test_extract_next_data_invalid_json_raises() -> None:
    """extract_next_data must raise ParseError on invalid JSON."""
    from listings_scraper.vendor_clients.domain.exceptions import ParseError
    html = '<script id="__NEXT_DATA__" type="application/json">{bad json</script>'
    with pytest.raises(ParseError):
        extract_next_data(html)


# ---------------------------------------------------------------------------
# Sample output — verify spot-checks on known listings from fixture
# ---------------------------------------------------------------------------


def test_parse_specific_listing_2020591534(paddington_next_data: dict) -> None:
    """Spot-check: 49 Reading Street listing with 'Price Guide $12M $12.5M'."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    listing = next(
        (l for l in listings if l.external_listing_id == "2020591534"), None
    )
    assert listing is not None, "Expected listing 2020591534 in results"
    assert "49 Reading Street" in listing.formatted_address
    assert listing.bedrooms == 5
    assert listing.bathrooms == 3
    assert listing.land_size_sqm == 1634.0
    # Price Guide $12M $12.5M → RANGE(12_000_000, 12_500_000)
    assert listing.price_kind is PriceKind.RANGE
    assert listing.price == 12_000_000
    assert listing.price_high == 12_500_000


def test_parse_specific_listing_2020616645(paddington_next_data: dict) -> None:
    """Spot-check: 'Offers over $3,300,000' → PRICE(3_300_000)."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    listing = next(
        (l for l in listings if l.external_listing_id == "2020616645"), None
    )
    assert listing is not None, "Expected listing 2020616645 in results"
    assert listing.price_kind is PriceKind.PRICE
    assert listing.price == 3_300_000


def test_parse_specific_listing_auction(paddington_next_data: dict) -> None:
    """Spot-check: 'Auction' listing → PriceKind.AUCTION."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    auction_listings = [l for l in listings if l.price_kind is PriceKind.AUCTION]
    assert len(auction_listings) >= 1, "Expected at least one AUCTION listing"


def test_parse_specific_listing_contact_agent(paddington_next_data: dict) -> None:
    """Spot-check: 'Contact Agent' listing → PriceKind.CONTACT."""
    listings, _ = parse_next_data_listings(
        paddington_next_data, Category.FORSALE, _OBSERVED_AT
    )
    contact_listings = [l for l in listings if l.price_kind is PriceKind.CONTACT]
    assert len(contact_listings) >= 1, "Expected at least one CONTACT listing"
