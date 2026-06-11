"""Vendor-neutral client abstractions.

`VendorListing` is the canonical listing model produced by every vendor
client and consumed by `listing_reconciler`. `SearchPage` wraps a page of
results. `VendorClient` is a typing.Protocol that all client implementations
must satisfy. `PriceKind` classifies the pricing intent.

Deep module — no DB imports, no session imports.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict

from listings_scraper.vendor import Vendor


class PriceKind(str, Enum):
    """How to interpret the price field(s) on a VendorListing."""

    PRICE = "price"           # single asking/sale price
    RANGE = "range"           # price range (price=low, price_high=high)
    AUCTION = "auction"       # no disclosed price, auction method
    EOI = "eoi"               # expressions of interest
    CONTACT = "contact"       # contact agent
    RENT_WEEKLY = "rent_weekly"  # weekly rent (for-rent listings)
    UNKNOWN = "unknown"       # could not classify


class VendorListing(BaseModel):
    """Vendor-neutral listing model produced by every vendor client.

    Reconciler and worker loop operate exclusively on this type. Vendor
    clients are responsible for mapping their raw data into this shape.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    source: Vendor
    external_listing_id: str          # campaign-level id (OTH listing id, Domain int id)
    external_property_id: Optional[str] = None  # OTH property id; Domain == external_listing_id
    listing_url: Optional[str] = None           # canonical detail URL

    # Address
    formatted_address: str
    postcode: str
    state: Optional[str] = None
    suburb_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coords_are_approximate: bool = False

    # Features
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    land_size_sqm: Optional[float] = None
    property_type: Optional[str] = None

    # Marketing
    title: Optional[str] = None
    status: Optional[str] = None       # vendor-normalised status string
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None

    # Price
    raw_price_display: Optional[str] = None    # free-form display string (always populated when known)
    price: Optional[int] = None                # parsed numeric, may be NULL
    price_high: Optional[int] = None           # for ranges/guides
    price_kind: PriceKind = PriceKind.UNKNOWN

    observed_at: datetime


class SearchPage(BaseModel):
    """One page of search results returned by a vendor client.

    `raw_payloads[i]` is the verbatim vendor JSON object that produced
    `listings[i]`. The reconciler stores it verbatim as
    `listing_snapshot.raw_payload`.
    """

    listings: list[VendorListing]
    raw_payloads: list[dict]   # parallel to listings
    page: int                  # 0-indexed
    has_next: bool
    total: Optional[int] = None


class VendorClient(Protocol):
    """Protocol every vendor client must satisfy.

    Callers may type-hint against this Protocol without importing any
    vendor-specific implementation — keeps the worker loop vendor-neutral.
    """

    source: Vendor

    async def search(
        self,
        suburb: object,         # ResolvedSuburb — forward ref to avoid circular import
        category: object,       # Category
        filters: object,        # ListingFilters
        page: int,
        session: object,        # ScrapeSession
    ) -> SearchPage: ...
