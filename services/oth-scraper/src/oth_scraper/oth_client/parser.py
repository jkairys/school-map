"""Parse OTH search responses into typed `SearchPage` objects.

Designed against the recorded fixtures under `tests/fixtures/oth/`. Those
fixtures are the source of truth for response shape; if OTH changes its
schema, the fixtures need refreshing (re-run `scripts/capture_fixtures.py`)
and this parser updated in lockstep.

The parser is defensive about missing fields: OTH omits `address.location`
for some older sold properties, omits `landSize` for apartments, omits the
`listing` block entirely for `RecentlySold` records, and so on. Anything
optional in `OTHListing` may legitimately be `None`.
"""

import re
from typing import Any, Optional

from oth_scraper.oth_client.exceptions import ParseError
from oth_scraper.oth_client.types import (
    Category,
    OTHListing,
    PriceUnit,
    SearchPage,
)

# A `$1,485,000` or `$699,000` style amount, as it appears inside a free-text
# `displayPrice` for ForSale listings. We require at least one comma-separated
# group (i.e. >= 1000) so noise like "Early $2m" doesn't parse to "$2".
_DOLLAR_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+)")

# Sale-price floor for ForSale listings parsed out of free-text. Anything
# below this is almost certainly a parse mistake (e.g. "$2m" → 2) rather
# than a real asking price.
_FORSALE_MIN_PRICE = 100_000

# `landSize` is reported in this unit by OTH for AU residential data. If a
# different unit shows up we bail out — better to lose the field than emit
# a wrong sqm number that flows into the snapshot.
_LAND_SIZE_UNIT_SQM = "squareMeter"


def parse_search_response(
    body: dict[str, Any],
    *,
    category: Category,
    page: int,
) -> SearchPage:
    """Parse one OTH search response page into a `SearchPage`.

    `category` selects the per-category extraction rules (price source,
    status derivation, agency location). `page` is the requested page
    number; we trust OTH's `number` over it but fall back to `page` if the
    response omits the field.
    """
    if not isinstance(body, dict):
        raise ParseError(f"expected JSON object, got {type(body).__name__}")

    raw_content = body.get("content")
    if raw_content is None:
        raise ParseError("response missing 'content' array")
    if not isinstance(raw_content, list):
        raise ParseError("response 'content' is not a list")

    listings: list[OTHListing] = []
    raw_payloads: list[dict] = []
    for i, item in enumerate(raw_content):
        if not isinstance(item, dict):
            raise ParseError(f"content[{i}] is not an object: {type(item).__name__}")
        listings.append(_parse_listing(item, category, index=i))
        raw_payloads.append(item)

    total = _as_int(body.get("totalElements"), default=len(listings))
    page_number = _as_int(body.get("number"), default=page)
    # OTH responses include a boolean `last` flag indicating "this is the
    # final page". Default to True when missing so a malformed pagination
    # block doesn't loop forever.
    has_next = not bool(body.get("last", True))

    return SearchPage(
        listings=listings,
        raw_payloads=raw_payloads,
        total=total,
        page=page_number,
        has_next=has_next,
    )


def _parse_listing(item: dict[str, Any], category: Category, *, index: int) -> OTHListing:
    oth_id = item.get("othPropertyId")
    if oth_id is None or oth_id == "":
        raise ParseError(f"content[{index}] missing 'othPropertyId'")

    address = item.get("address") or {}
    formatted_address = address.get("formattedAddress") or ""
    if not formatted_address:
        raise ParseError(f"content[{index}] missing 'address.formattedAddress'")

    postcode = address.get("postCode") or ""
    location = address.get("location") or {}

    price, price_unit = _extract_price(item, category)
    agent_name, agency_name = _extract_agent_and_agency(item, category)
    status = _derive_status(item, category)

    return OTHListing(
        oth_property_id=str(oth_id),
        formatted_address=formatted_address,
        postcode=str(postcode),
        latitude=_as_float(location.get("lat")),
        longitude=_as_float(location.get("lon")),
        bedrooms=_as_int_optional(item.get("beds")),
        bathrooms=_as_int_optional(item.get("baths")),
        parking=_as_int_optional(item.get("carSpaces")),
        land_size_sqm=_extract_land_size_sqm(item),
        property_type=item.get("type"),
        agent_name=agent_name,
        agency_name=agency_name,
        listing_url=_extract_oth_web_url(item.get("links")),
        title=formatted_address,
        status=status,
        price=price,
        price_unit=price_unit,
    )


def _extract_price(
    item: dict[str, Any], category: Category
) -> tuple[Optional[int], PriceUnit]:
    if category is Category.RECENTLYSOLD:
        last_sale = item.get("lastSale") or {}
        return _as_int_optional(last_sale.get("salePrice")), PriceUnit.TOTAL

    listing = item.get("listing") or {}
    if category is Category.FORRENT:
        # OTH gives us a clean integer weekly rent on rental listings; trust it.
        return _as_int_optional(listing.get("price")), PriceUnit.WEEKLY

    # ForSale: most cards expose a free-text displayPrice ("For Sale",
    # "Auction", "Offers over $2,450,000"). We extract a dollar figure when
    # one is present; otherwise the price is genuinely undisclosed.
    parsed = _parse_display_price(listing.get("displayPrice"))
    if parsed is not None and parsed < _FORSALE_MIN_PRICE:
        # Defensive: don't propagate a price that's almost certainly a
        # parse artefact (e.g. "$2m" → 2).
        parsed = None
    return parsed, PriceUnit.TOTAL


def _parse_display_price(display: Optional[str]) -> Optional[int]:
    if not display:
        return None
    match = _DOLLAR_AMOUNT_RE.search(display)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_agent_and_agency(
    item: dict[str, Any], category: Category
) -> tuple[Optional[str], Optional[str]]:
    if category is Category.RECENTLYSOLD:
        agency = (item.get("lastSale") or {}).get("sellingAgency") or {}
    else:
        agency = (item.get("listing") or {}).get("agency") or {}

    agency_name = agency.get("name") or None

    agents = agency.get("agents") or []
    if agents:
        # Multi-agent listings: by spec we keep the first agent's name only.
        first = agents[0]
        if isinstance(first, dict):
            agent_name = first.get("name") or None
        else:
            agent_name = None
    else:
        agent_name = None

    return agent_name, agency_name


def _derive_status(item: dict[str, Any], category: Category) -> str:
    if category is Category.RECENTLYSOLD:
        return "sold"
    if category is Category.FORRENT:
        return "current"
    # ForSale: surface the under-offer transition so the snapshot diff can
    # detect it as a change. Everything else is treated as a live listing.
    if item.get("underOffer") is True:
        return "under_offer"
    return "current"


def _extract_land_size_sqm(item: dict[str, Any]) -> Optional[float]:
    raw = item.get("landSize")
    if raw is None:
        return None
    unit = item.get("landSizeUnit")
    if unit and unit != _LAND_SIZE_UNIT_SQM:
        # Unknown unit — rather than guess, drop the field. We can revisit
        # if a non-sqm unit actually appears in production fixtures.
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extract_oth_web_url(links: Any) -> Optional[str]:
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "othWebUrl":
            href = link.get("href")
            if isinstance(href, str) and href:
                return href
    return None


def _as_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_int_optional(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
