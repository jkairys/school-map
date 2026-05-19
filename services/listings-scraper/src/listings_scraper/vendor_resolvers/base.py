"""Vendor-neutral suburb resolver abstractions.

`ResolvedSuburb` is the canonical resolved suburb model shared across all
vendor resolvers and used in DB lookups. `VendorSuburbResolver` is the
Protocol that all resolver implementations must satisfy.

Deep module — no DB imports here. The concrete resolver implementations
(`vendor_resolvers/oth/`) import from `db.models` as needed.
"""

from datetime import datetime
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict

from listings_scraper.vendor import Vendor


class ResolvedSuburb(BaseModel):
    """A confidently resolved suburb, persisted in the `suburb` table.

    Gains a `source: Vendor` field so the resolver can tag which portal's
    slug/URL format applies. The `slug` field carries the vendor-specific
    URL fragment (OTH: `"paddington-4064"`, Domain: `"paddington-qld-4064"`).

    PR 2 renames `oth_slug` → `slug` in the DB; for PR 1 we map `oth_slug`
    to `slug` at the Python level so the model is vendor-neutral.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    postcode: str
    state: str
    source: Vendor = Vendor.OTH   # default for backward-compat during PR 1
    slug: Optional[str] = None    # vendor-specific slug; maps from oth_slug in PR 1

    resolved_at: datetime


class Match(BaseModel):
    """One candidate from a suburb autocomplete response."""

    name: str
    postcode: str
    state: str
    source: Vendor = Vendor.OTH
    slug: Optional[str] = None   # vendor-specific slug fragment


class VendorSuburbResolver(Protocol):
    """Protocol every suburb resolver must satisfy."""

    source: Vendor

    async def resolve(
        self,
        name: str,
        *,
        db: object,              # AsyncSession — forward ref to avoid circular import
        postcode: Optional[str] = None,
        state: Optional[str] = None,
    ) -> "ResolvedSuburb | list[Match]": ...
