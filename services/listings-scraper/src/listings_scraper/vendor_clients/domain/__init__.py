"""Domain (domain.com.au) vendor client.

Re-exports the public surface for the Domain vendor client:
- `DomainApiClient`: implements the VendorClient protocol
- `extract_next_data`: extracts __NEXT_DATA__ JSON from HTML
- `parse_next_data_listings`: maps listingsMap entries to VendorListing

Deep module — no DB imports. Uses camoufox via scrape_session.page().
"""

from listings_scraper.vendor_clients.domain.client import DomainApiClient
from listings_scraper.vendor_clients.domain.next_data import extract_next_data
from listings_scraper.vendor_clients.domain.parser import parse_next_data_listings

__all__ = [
    "DomainApiClient",
    "extract_next_data",
    "parse_next_data_listings",
]
