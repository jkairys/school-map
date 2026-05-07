from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Category(str, Enum):
    """Search categories supported by the v1 service."""

    FORSALE = "forsale"
    FORRENT = "forrent"
    RECENTLYSOLD = "recentlysold"

    @property
    def oth_name(self) -> str:
        """Mixed-case form OTH's API expects in the request payload."""
        return _OTH_CATEGORY_NAMES[self]


_OTH_CATEGORY_NAMES = {
    Category.FORSALE: "SaleListing",
    Category.FORRENT: "RentalListing",
    Category.RECENTLYSOLD: "RecentlySold",
}


class PropertyType(str, Enum):
    """Property-type filter values. Strings match OTH's filter codes."""

    HOUSE = "House"
    APARTMENT = "Apartment"
    TOWNHOUSE = "Townhouse"
    UNIT = "Unit"
    LAND = "Land"
    RURAL = "Rural"


class PriceUnit(str, Enum):
    """How to interpret OTHListing.price."""

    TOTAL = "total"  # forsale asking price, recentlysold sale price (AUD)
    WEEKLY = "weekly"  # forrent advertised weekly rent (AUD/week)


class ResolvedSuburb(BaseModel):
    """A suburb that has been disambiguated against OTH's autocomplete."""

    model_config = ConfigDict(frozen=True)

    name: str  # canonical suburb name, e.g. "Paddington"
    postcode: str  # e.g. "4064"
    state: str  # e.g. "QLD"
    oth_slug: Optional[str] = None  # e.g. "paddington-qld-4064"


class ListingFilters(BaseModel):
    """User-supplied filters applied to a search.

    Empty/None fields mean unfiltered on that dimension.
    """

    model_config = ConfigDict(frozen=True)

    beds_min: Optional[int] = None
    beds_max: Optional[int] = None
    property_types: tuple[PropertyType, ...] = ()
    price_min: Optional[int] = None
    price_max: Optional[int] = None


class OTHListing(BaseModel):
    """A single listing parsed from an OTH search response.

    Carries every field the snapshot schema cares about. Fields OTH does not
    return for a given listing are `None` (notably `latitude`/`longitude` for
    older sold properties, and `land_size_sqm` for apartments).
    """

    oth_property_id: str
    formatted_address: str
    postcode: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking: Optional[int] = None
    land_size_sqm: Optional[float] = None
    property_type: Optional[str] = None

    agent_name: Optional[str] = None  # first agent if multiple are listed
    agency_name: Optional[str] = None

    listing_url: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None  # raw OTH status string

    price: Optional[int] = None
    price_unit: PriceUnit = PriceUnit.TOTAL


class SearchPage(BaseModel):
    """One page of search results plus pagination metadata."""

    listings: list[OTHListing] = Field(default_factory=list)
    total: int = 0
    page: int = 0
    has_next: bool = False
