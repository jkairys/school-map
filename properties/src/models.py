"""Data models for the Brisbane Property Scraper."""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class SoldProperty:
    """Represents a sold property with key details."""
    address: str
    suburb: str
    postcode: str
    sale_price: Optional[int]
    sale_date: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    parking: Optional[int]
    land_size_sqm: Optional[int]
    property_type: str
    description: str
    listing_url: str
    agent_name: Optional[str]
    agency_name: Optional[str]

    def to_dict(self) -> dict:
        """Convert the property to a dictionary."""
        return asdict(self)
