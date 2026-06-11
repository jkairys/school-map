"""Live end-to-end smoke test against real Domain.com.au.

Skipped by default. Runs only when ``RUN_LIVE_DOMAIN_TESTS=1`` is set in
the environment. Intended to be run manually before releases — never in CI.

The test:
1. Boots a real ScrapeSession with DOMAIN_CONFIG (camoufox-backed).
2. Instantiates DomainApiClient and calls .search() for Paddington QLD 4064
   FORSALE, page 0.
3. Asserts that ≥1 listing came back with sane fields.

This test WILL be slow (camoufox startup + Akamai + live HTTP fetch).
It is explicitly marked @pytest.mark.live and skipped unless opt-in env is set.

To run:
    RUN_LIVE_DOMAIN_TESTS=1 uv run pytest \
        services/listings-scraper/tests/e2e/test_live_domain.py -s -v
"""

import os

import pytest

LIVE_FLAG = "RUN_LIVE_DOMAIN_TESTS"

pytestmark = pytest.mark.skipif(
    os.environ.get(LIVE_FLAG) != "1",
    reason=f"set {LIVE_FLAG}=1 to run the live Domain smoke test",
)

SUBURB_NAME = "Paddington"
SUBURB_STATE = "QLD"
SUBURB_POSTCODE = "4064"


@pytest.mark.live
async def test_live_domain_search_forsale() -> None:
    """End-to-end: DomainApiClient + ScrapeSession(DOMAIN_CONFIG) against live Domain."""
    from datetime import datetime, timezone

    from listings_scraper.scrape_session import ScrapeSession
    from listings_scraper.scrape_session.configs.domain import DOMAIN_CONFIG
    from listings_scraper.vendor import Vendor
    from listings_scraper.vendor_clients.base import PriceKind
    from listings_scraper.vendor_clients.domain import DomainApiClient
    from listings_scraper.vendor_clients.oth.types import Category, ListingFilters
    from listings_scraper.vendor_resolvers.base import ResolvedSuburb

    # Build a minimal ResolvedSuburb with the Domain slug format
    suburb = ResolvedSuburb(
        id=1,
        name=SUBURB_NAME,
        postcode=SUBURB_POSTCODE,
        state=SUBURB_STATE,
        source=Vendor.DOMAIN,
        slug=f"{SUBURB_NAME.lower()}-{SUBURB_STATE.lower()}-{SUBURB_POSTCODE}",
        resolved_at=datetime.now(tz=timezone.utc),
    )

    client = DomainApiClient()
    filters = ListingFilters()

    async with ScrapeSession(bootstrap_config=DOMAIN_CONFIG) as session:
        page = await client.search(suburb, Category.FORSALE, filters, 0, session)

    print(f"\nlive Domain smoke: got {len(page.listings)} listings, has_next={page.has_next}")

    assert len(page.listings) >= 1, (
        "Expected ≥1 listing from live Domain search for Paddington QLD 4064 FORSALE"
    )

    # Verify sane fields on at least some listings
    listings_with_address = [l for l in page.listings if l.formatted_address]
    assert len(listings_with_address) >= 1, "Expected at least one listing with a formatted address"

    listings_with_beds = [l for l in page.listings if l.bedrooms is not None]
    print(f"  listings with beds: {len(listings_with_beds)}/{len(page.listings)}")
    assert len(listings_with_beds) >= 1, "Expected at least some listings with bedrooms populated"

    for listing in page.listings:
        assert listing.source is Vendor.DOMAIN, f"listing {listing.external_listing_id} has wrong source"
        assert listing.postcode == SUBURB_POSTCODE, f"unexpected postcode: {listing.postcode}"
        if listing.listing_url:
            assert listing.listing_url.startswith("https://www.domain.com.au/"), (
                f"listing_url not absolute: {listing.listing_url}"
            )

    # Print a few sample listings for human inspection
    print("\nSample listings:")
    for listing in page.listings[:3]:
        print(
            f"  [{listing.external_listing_id}] {listing.formatted_address} "
            f"beds={listing.bedrooms} baths={listing.bathrooms} "
            f"price_kind={listing.price_kind.value} price={listing.raw_price_display!r}"
        )
