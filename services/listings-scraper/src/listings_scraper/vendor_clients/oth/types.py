from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
