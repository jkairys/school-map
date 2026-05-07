"""OTH search-API request payload builder.

Pure functions, no I/O. The output is the JSON body posted to
`POST https://www.onthehouse.com.au/odin/api/composite/search`.
"""

from typing import Any

from oth_scraper.oth_client.types import (
    Category,
    ListingFilters,
    PropertyType,
    ResolvedSuburb,
)

SEARCH_URL = "https://www.onthehouse.com.au/odin/api/composite/search"
DEFAULT_PAGE_SIZE = 24

# Sort applied per category. RecentlySold is sorted by most-recent sale; the
# active categories sort by listing date so newly-listed properties surface first.
_CATEGORY_SORT: dict[Category, list[dict[str, str]]] = {
    Category.FORSALE: [{"listing.listedDate": "desc"}],
    Category.FORRENT: [{"listing.listedDate": "desc"}],
    Category.RECENTLYSOLD: [{"lastSale.eventDate": "desc"}],
}

# Per-category JSON path for the price filter range. SaleListing uses the
# asking price, RentalListing uses weekly rent, RecentlySold uses the
# realised sale price.
_PRICE_FIELD: dict[Category, str] = {
    Category.FORSALE: "listing.price",
    Category.FORRENT: "listing.weeklyRent",
    Category.RECENTLYSOLD: "lastSale.price",
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

    The payload always contains exactly one entry in `query.queries` describing
    the suburb-and-category target. Filter fields are added under `query` only
    when the corresponding filter dimension is set, so an "unfiltered" search
    produces the minimal payload.
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

    query: dict[str, Any] = {"queries": [target]}

    bed_range = _bed_range(filters)
    if bed_range is not None:
        query["bedrooms"] = bed_range

    if filters.property_types:
        query["propertyTypes"] = [_property_type_value(t) for t in filters.property_types]

    price_range = _price_range(filters)
    if price_range is not None:
        query[_PRICE_FIELD[category]] = price_range

    return {
        "size": size,
        "number": page,
        "sort": sort,
        "query": query,
    }


def _bed_range(filters: ListingFilters) -> dict[str, int] | None:
    if filters.beds_min is None and filters.beds_max is None:
        return None
    out: dict[str, int] = {}
    if filters.beds_min is not None:
        out["min"] = filters.beds_min
    if filters.beds_max is not None:
        out["max"] = filters.beds_max
    return out


def _price_range(filters: ListingFilters) -> dict[str, int] | None:
    if filters.price_min is None and filters.price_max is None:
        return None
    out: dict[str, int] = {}
    if filters.price_min is not None:
        out["min"] = filters.price_min
    if filters.price_max is not None:
        out["max"] = filters.price_max
    return out


def _property_type_value(t: PropertyType) -> str:
    # PropertyType enum values are already in OTH's expected casing.
    return t.value
