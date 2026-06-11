"""Backward-compat shim — `oth_client` moved to `vendor_clients.oth`.

This shim re-exports the public surface so any remaining code that imports
from `listings_scraper.oth_client` continues to work during PR 1. PR 3
will clean up these aliases.

NOTE: `SearchPage` and `OTHListing` here come from the vendor_clients layer,
not the old types. `OTHListing` is removed; use `VendorListing` from
`listings_scraper.vendor_clients.base` instead.
"""

from listings_scraper.vendor_clients.oth.client import OTHApiClient
from listings_scraper.vendor_clients.oth.exceptions import ParseError
from listings_scraper.vendor_clients.oth.types import (
    Category,
    ListingFilters,
    PropertyType,
)
from listings_scraper.vendor_clients.base import PriceKind as PriceUnit  # alias
from listings_scraper.vendor_clients.base import SearchPage, VendorListing as OTHListing
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

__all__ = [
    "Category",
    "ListingFilters",
    "OTHApiClient",
    "OTHListing",
    "ParseError",
    "PriceUnit",
    "PropertyType",
    "ResolvedSuburb",
    "SearchPage",
]
