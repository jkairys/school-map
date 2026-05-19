"""Coordination layer for suburb resolution. Both REST and CLI call this."""

from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.suburb_resolver import Match, ResolvedSuburb, resolve


async def resolve_suburb(
    name: str,
    *,
    session: AsyncSession,
    postcode: str | None = None,
    state: str | None = None,
) -> ResolvedSuburb | list[Match]:
    """Resolve a suburb name. Thin pass-through to the deep resolver."""
    return await resolve(name, session=session, postcode=postcode, state=state)
