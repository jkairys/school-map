"""Backward-compat shim — types moved to vendor_clients.oth.types / vendor_clients.base."""
from listings_scraper.vendor_clients.oth.types import (  # noqa: F401
    Category,
    ListingFilters,
    PropertyType,
)
from listings_scraper.vendor_clients.base import (  # noqa: F401
    PriceKind as PriceUnit,
    SearchPage,
    VendorListing as OTHListing,
)
from listings_scraper.vendor_resolvers.base import ResolvedSuburb  # noqa: F401
