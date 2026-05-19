"""Coordination layer for suburb resolution. Both REST and CLI call this.

Dispatches to the appropriate vendor resolver based on `source`:
- Vendor.OTH → OTHSuburbResolver (autocomplete-based, network call)
- Vendor.DOMAIN → DomainSuburbResolver (deterministic, requires postcode + state)

The `source` parameter defaults to Vendor.OTH for backward compatibility with
existing callers that do not pass a source.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.suburb_resolver import Match, ResolvedSuburb, resolve
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_resolvers.base import ResolvedSuburb


async def resolve_suburb(
    name: str,
    *,
    session: AsyncSession,
    postcode: Optional[str] = None,
    state: Optional[str] = None,
    source: Vendor = Vendor.OTH,
) -> "ResolvedSuburb | list[Match]":
    """Resolve a suburb name. Dispatches to the appropriate vendor resolver.

    Args:
        name: The suburb name to resolve.
        session: Async DB session for cache lookups and persistence.
        postcode: Optional postcode disambiguator (required for Domain).
        state: Optional state code disambiguator (required for Domain).
        source: Which vendor's resolver to use. Defaults to OTH for backward compat.

    Returns:
        A ResolvedSuburb on a confident single match, or a list[Match] when
        OTH returns multiple candidates.

    Raises:
        SuburbResolutionError: For Domain, if postcode or state is missing.
        NoMatchError: For OTH, if no matching suburb is found.
    """
    if source == Vendor.DOMAIN:
        from listings_scraper.vendor_resolvers.domain.resolver import DomainSuburbResolver
        resolver = DomainSuburbResolver()
        return await resolver.resolve(name, db=session, postcode=postcode, state=state)

    # Default: OTH resolver (autocomplete-based)
    return await resolve(name, session=session, postcode=postcode, state=state)
