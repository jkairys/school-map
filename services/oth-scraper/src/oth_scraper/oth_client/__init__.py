"""OTH search-API client.

A deep module: knows everything about OnTheHouse's search request/response
shapes and nothing about the database, the worker loop, or session bootstrap.
The caller supplies an `httpx.AsyncClient` carrying any cookies/headers the
upstream anti-bot layer needs.
"""

from oth_scraper.oth_client.client import OTHApiClient
from oth_scraper.oth_client.exceptions import ParseError
from oth_scraper.oth_client.types import (
    Category,
    ListingFilters,
    OTHListing,
    PriceUnit,
    PropertyType,
    ResolvedSuburb,
    SearchPage,
)

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
