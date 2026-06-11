"""OTH (onthehouse.com.au) vendor client.

Re-exports the public surface so test imports like
`from listings_scraper.vendor_clients.oth import OTHApiClient` continue to
work after the module restructure.
"""

from listings_scraper.vendor_clients.oth.client import OTHApiClient
from listings_scraper.vendor_clients.oth.exceptions import ParseError
from listings_scraper.vendor_clients.oth.types import (
    Category,
    ListingFilters,
    PropertyType,
)
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

__all__ = [
    "Category",
    "ListingFilters",
    "OTHApiClient",
    "ParseError",
    "PropertyType",
    "ResolvedSuburb",
]
