"""Parse Domain __NEXT_DATA__ search payloads into vendor-neutral VendorListing objects.

Designed against the captured fixture at
`tests/fixtures/domain/next_data_search_paddington.json`.
The authoritative shape reference is `docs/domain-scraper/PHASE_0_SPIKE.md`.

Domain search results are in:
  props.pageProps.componentProps.listingsMap[<id>].listingModel

where `<id>` is the listing's integer ID (as a string dict key).

Status rule (snapshot-churn policy decision):
  - Only "Under offer" / "Sold" (and case variants) influence the `status`
    field — they signal a real state transition worth capturing in the diff.
  - Tags like "New" and "Updated" are noise: they rotate as Domain freshens
    its cache and would cause a new snapshot on every scrape without any
    meaningful data change. These are deliberately ignored.

V1 limitation (Domain URL filters):
  - This parser does not apply any listing-level filtering. The URL the
    client constructs does not encode bedrooms/price filters in v1 — all
    listings from Domain's paginated search are returned and stored. A
    future PR will add URL-level filter query parameters; for now the
    reconciler stores everything and downstream consumers can filter on the
    stored fields.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from listings_scraper.price_normaliser import parse_domain_listing
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import VendorListing
from listings_scraper.vendor_clients.domain.exceptions import ParseError

logger = logging.getLogger(__name__)

_DOMAIN_BASE_URL = "https://www.domain.com.au"

# Tags that indicate a meaningful status transition. Tags NOT in this set
# (e.g. "New", "Updated") are ignored to avoid snapshot churn — they rotate
# as Domain refreshes its listing cache and carry no durable state signal.
_STATUS_TAG_MAP: dict[str, str] = {
    "under offer": "under_offer",
    "sold": "sold",
}


def parse_next_data_listings(
    next_data: dict[str, Any],
    category: object,  # Category — forward ref to avoid circular import
    observed_at: datetime,
) -> tuple[list[VendorListing], list[dict]]:
    """Extract VendorListing objects from a Domain __NEXT_DATA__ search payload.

    Args:
        next_data: Parsed __NEXT_DATA__ dict from a Domain search page.
        category: The listing category (Category enum from vendor_clients.oth.types).
            Passed to price_normaliser for correct price classification.
        observed_at: The timestamp to stamp on every VendorListing.

    Returns:
        A tuple of (listings, raw_payloads) where raw_payloads[i] is the
        verbatim `listingModel` dict for listings[i]. The raw_payloads list
        is stored as `listing_snapshot.raw_payload` for auditability.

    Raises:
        ParseError: If the __NEXT_DATA__ structure does not contain
            the expected `listingsMap` path.
    """
    try:
        component_props = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("componentProps", {})
        )
    except (AttributeError, TypeError) as exc:
        raise ParseError(f"__NEXT_DATA__ has unexpected structure: {exc}") from exc

    listings_map: dict[str, Any] = component_props.get("listingsMap") or {}

    listings: list[VendorListing] = []
    raw_payloads: list[dict] = []

    for listing_id_str, entry in listings_map.items():
        if not isinstance(entry, dict):
            logger.warning("domain parser: listingsMap[%r] is not a dict, skipping", listing_id_str)
            continue
        listing_model: dict[str, Any] = entry.get("listingModel") or {}
        if not listing_model:
            logger.warning("domain parser: listingsMap[%r] has no listingModel, skipping", listing_id_str)
            continue

        try:
            vendor_listing = _parse_listing_model(
                listing_id_str, listing_model, category, observed_at
            )
        except Exception:
            logger.warning(
                "domain parser: failed to parse listing %r — skipping",
                listing_id_str,
                exc_info=True,
            )
            continue

        listings.append(vendor_listing)
        raw_payloads.append(listing_model)

    return listings, raw_payloads


def _parse_listing_model(
    listing_id_str: str,
    lm: dict[str, Any],
    category: object,
    observed_at: datetime,
) -> VendorListing:
    """Map one Domain listingModel dict to a VendorListing."""
    # Identity
    # The int key from listingsMap is the Domain listing ID. Domain has no
    # separate property ID exposed in search results — we use the same ID
    # for both external_listing_id and external_property_id. This means
    # the reconciler's per-source (source, external_property_id) unique
    # index will correctly dedup Domain listings across scrape runs.
    external_listing_id = listing_id_str
    external_property_id = listing_id_str  # Domain: no separate property ID in search

    # URL
    raw_url: Optional[str] = lm.get("url")
    listing_url: Optional[str] = None
    if raw_url:
        listing_url = f"{_DOMAIN_BASE_URL}{raw_url}" if raw_url.startswith("/") else raw_url

    # Address
    address: dict[str, Any] = lm.get("address") or {}
    street = address.get("street") or ""
    suburb = address.get("suburb") or ""
    state = address.get("state") or ""
    postcode = address.get("postcode") or ""

    # Build formatted_address in a human-readable way, mirroring what
    # Domain displays: "9 Belmont Crescent, Paddington QLD 4064"
    parts = [p for p in [street, suburb] if p]
    locality = " ".join(p for p in [state, postcode] if p)
    if locality:
        parts.append(locality)
    formatted_address = ", ".join(parts) if parts else ""

    latitude = _as_float(address.get("lat"))
    longitude = _as_float(address.get("lng"))

    # Features
    features: dict[str, Any] = lm.get("features") or {}
    bedrooms = _as_int_optional(features.get("beds"))
    bathrooms = _as_int_optional(features.get("baths"))
    parking = _as_int_optional(features.get("parking"))
    land_size_sqm = _as_float(features.get("landSize"))
    property_type: Optional[str] = features.get("propertyType") or None

    # Branding / agent info
    branding: dict[str, Any] = lm.get("branding") or {}
    # `agentName` is the first/primary agent; `agentNames` is a comma-joined
    # string of all agent names. We use the scalar field for consistency.
    agent_name: Optional[str] = branding.get("agentName") or None
    agency_name: Optional[str] = branding.get("brandName") or None

    # Price
    raw_price_display: Optional[str] = lm.get("price") or None
    normalised = parse_domain_listing(lm, category)

    # Status — only map real transition tags; ignore noise tags (see module docstring)
    status = _derive_status(lm)

    return VendorListing(
        source=Vendor.DOMAIN,
        external_listing_id=external_listing_id,
        external_property_id=external_property_id,
        listing_url=listing_url,
        formatted_address=formatted_address,
        postcode=str(postcode),
        state=str(state) if state else None,
        suburb_name=str(suburb) if suburb else None,
        latitude=latitude,
        longitude=longitude,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        parking=parking,
        land_size_sqm=land_size_sqm,
        property_type=property_type,
        title=formatted_address,
        status=status,
        agent_name=agent_name,
        agency_name=agency_name,
        raw_price_display=raw_price_display,
        price=normalised.low,
        price_high=normalised.high,
        price_kind=normalised.kind,
        observed_at=observed_at,
    )


def _derive_status(lm: dict[str, Any]) -> Optional[str]:
    """Derive status from a Domain listingModel's tags field.

    Policy: ONLY map "Under offer" and "Sold" (case-insensitive) to a
    status value. Tags "New" and "Updated" are intentionally ignored to
    prevent snapshot churn — they indicate Domain cache freshness, not
    actual listing state changes.
    """
    tags: dict[str, Any] = lm.get("tags") or {}
    tag_text: Optional[str] = tags.get("tagText")
    if not tag_text:
        return None
    normalised_tag = tag_text.strip().lower()
    return _STATUS_TAG_MAP.get(normalised_tag)


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
