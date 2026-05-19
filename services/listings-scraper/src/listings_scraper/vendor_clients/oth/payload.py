"""OTH search-API request payload builder.

Pure functions, no I/O. The output is the JSON body posted to
`POST https://www.onthehouse.com.au/odin/api/composite/search`.

Filter shape was captured from the live OTH frontend (see
`tests/oth_client/test_payload.py` for the snapshot fixtures). Every filter
dimension is a flat string-valued key inside the per-suburb target object
under ``query.queries[i]`` — NOT nested under ``query`` and NOT structured
as a ``{min, max}`` sub-object. The categories also disagree on the price
key: SaleListing/RecentlySold use ``priceMin``/``priceMax`` while
RentalListing uses ``forRentPriceMin``/``forRentPriceMax``.

Sending the wrong shape (e.g. ``bedrooms: {min: 1}`` under ``query``) causes
OTH to respond ``HTTP 400 {"error": "An unexpected error has occurred"}``.
"""

from typing import Any

from listings_scraper.vendor_clients.oth.types import (
    Category,
    ListingFilters,
    PropertyType,
)
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

SEARCH_URL = "https://www.onthehouse.com.au/odin/api/composite/search"
DEFAULT_PAGE_SIZE = 24

# Sort applied per category. RecentlySold is sorted by most-recent sale; the
# active categories sort by listing date so newly-listed properties surface first.
_CATEGORY_SORT: dict[Category, list[dict[str, str]]] = {
    Category.FORSALE: [{"listing.listedDate": "desc"}],
    Category.FORRENT: [{"listing.listedDate": "desc"}],
    Category.RECENTLYSOLD: [{"lastSale.eventDate": "desc"}],
}

# Per-category JSON keys for the price filter min/max. SaleListing and
# RecentlySold both key off ``priceMin``/``priceMax``; RentalListing
# uses a distinct ``forRentPriceMin``/``forRentPriceMax`` pair (verified
# live against the OTH frontend).
_PRICE_KEYS: dict[Category, tuple[str, str]] = {
    Category.FORSALE: ("priceMin", "priceMax"),
    Category.FORRENT: ("forRentPriceMin", "forRentPriceMax"),
    Category.RECENTLYSOLD: ("priceMin", "priceMax"),
}

# OTH's "live listing" categories carry an explicit `status` discriminator.
# RecentlySold queries do not.
_REQUIRES_STATUS_CURRENT = {Category.FORSALE, Category.FORRENT}


def build_search_payload(
    suburb: ResolvedSuburb,
    category: Category,
    filters: ListingFilters,
    page: int,
    *,
    size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Build the JSON body for an OTH search request.

    The payload always contains exactly one entry in ``query.queries``
    describing the suburb-and-category target. Every filter dimension is
    inlined into that target object — OTH rejects nested ``{min, max}``
    structures and rejects filters at the ``query`` level. Categories that
    are unfiltered on a given dimension simply omit the corresponding
    key(s).
    """
    sort = _CATEGORY_SORT[category]
    target: dict[str, Any] = {
        "category": category.oth_name,
        "stateCode": suburb.state.upper(),
        "suburb": suburb.name.lower(),
        "postCode": suburb.postcode,
    }
    if category in _REQUIRES_STATUS_CURRENT:
        target["status"] = "current"

    if filters.beds_min is not None:
        target["bedsMin"] = str(filters.beds_min)
    if filters.beds_max is not None:
        target["bedsMax"] = str(filters.beds_max)

    price_min_key, price_max_key = _PRICE_KEYS[category]
    if filters.price_min is not None:
        target[price_min_key] = str(filters.price_min)
    if filters.price_max is not None:
        target[price_max_key] = str(filters.price_max)

    if filters.property_types:
        target["types"] = [_property_type_value(t) for t in filters.property_types]

    return {
        "size": size,
        "number": page,
        "sort": sort,
        "query": {"queries": [target]},
    }


def _property_type_value(t: PropertyType) -> str:
    # PropertyType enum values are already in OTH's expected casing.
    return t.value
