"""Parse OTH search responses into vendor-neutral `VendorListing` objects.

Designed against the recorded fixtures under `tests/fixtures/oth/`. Those
fixtures are the source of truth for response shape; if OTH changes its
schema, the fixtures need refreshing (re-run `scripts/capture_fixtures.py`)
and this parser updated in lockstep.

The parser is defensive about missing fields: OTH omits `address.location`
for some older sold properties, omits `landSize` for apartments, omits the
`listing` block entirely for `RecentlySold` records, and so on. Anything
optional in `VendorListing` may legitimately be `None`.

Price parsing is delegated to `price_normaliser.parse_oth_listing()` which
owns the OTH-specific regex and classification rules.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from listings_scraper.price_normaliser import parse_oth_listing
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import SearchPage, VendorListing
from listings_scraper.vendor_clients.oth.exceptions import ParseError
from listings_scraper.vendor_clients.oth.types import Category

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
    """Parse one OTH search response page into a vendor-neutral `SearchPage`.

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

    observed_at = datetime.now(tz=timezone.utc)

    listings: list[VendorListing] = []
    raw_payloads: list[dict] = []
    for i, item in enumerate(raw_content):
        if not isinstance(item, dict):
            raise ParseError(f"content[{i}] is not an object: {type(item).__name__}")
        listings.append(_parse_listing(item, category, index=i, observed_at=observed_at))
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


def _parse_listing(
    item: dict[str, Any],
    category: Category,
    *,
    index: int,
    observed_at: datetime,
) -> VendorListing:
    oth_id = item.get("othPropertyId")
    if oth_id is None or oth_id == "":
        raise ParseError(f"content[{index}] missing 'othPropertyId'")

    address = item.get("address") or {}
    formatted_address = address.get("formattedAddress") or ""
    if not formatted_address:
        raise ParseError(f"content[{index}] missing 'address.formattedAddress'")

    postcode = address.get("postCode") or ""
    location = address.get("location") or {}

    normalised = parse_oth_listing(item, category)
    agent_name, agency_name = _extract_agent_and_agency(item, category)
    status = _derive_status(item, category)

    external_property_id = str(oth_id)
    listing_url = _extract_oth_web_url(item.get("links"))

    # OTH doesn't surface a stable per-campaign listing ID on search-list
    # responses. We derive a deterministic external_listing_id from the
    # property ID (unique per property, so per-campaign dedup is approximate).
    external_listing_id = external_property_id

    return VendorListing(
        source=Vendor.OTH,
        external_listing_id=external_listing_id,
        external_property_id=external_property_id,
        listing_url=listing_url,
        formatted_address=formatted_address,
        postcode=str(postcode),
        state=None,   # OTH doesn't reliably return state on listing results
        suburb_name=None,  # OTH doesn't return suburb_name in listing results
        latitude=_as_float(location.get("lat")),
        longitude=_as_float(location.get("lon")),
        bedrooms=_as_int_optional(item.get("beds")),
        bathrooms=_as_int_optional(item.get("baths")),
        parking=_as_int_optional(item.get("carSpaces")),
        land_size_sqm=_extract_land_size_sqm(item),
        property_type=item.get("type"),
        agent_name=agent_name,
        agency_name=agency_name,
        title=formatted_address,
        status=status,
        raw_price_display=normalised.display,
        price=normalised.low,
        price_high=normalised.high,
        price_kind=normalised.kind,
        observed_at=observed_at,
    )



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
