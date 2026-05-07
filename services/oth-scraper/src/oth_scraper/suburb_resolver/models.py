from datetime import datetime

from pydantic import BaseModel, Field


class Match(BaseModel):
    """One candidate from the OTH autocomplete response."""

    name: str = Field(..., description="Suburb name as returned by OTH")
    postcode: str = Field(..., description="Postcode (4-digit AU)")
    state: str = Field(..., description="State code, e.g. QLD, NSW, VIC")
    oth_slug: str = Field(..., description="Slug used in OTH URLs, e.g. 'little-mountain-4551'")


class ResolvedSuburb(BaseModel):
    """A confidently resolved suburb, persisted in the `suburb` table."""

    id: int
    name: str
    postcode: str
    state: str
    oth_slug: str
    resolved_at: datetime

    model_config = {"from_attributes": True}
