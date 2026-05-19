"""Domain suburb resolver — maps suburb names to Domain URL slugs.

Domain URLs are predictable: the slug is
    `<name-lowercased-hyphenated>-<state-lowercased>-<postcode>`
e.g. `paddington-qld-4064`.

This resolver does NOT call out to the network. It computes the slug
deterministically and persists a Suburb row to the DB for the
`(source=Vendor.DOMAIN, name, postcode, state)` combination.

Unlike the OTH resolver (which can autocomplete a suburb name to
postcode/state via an API call), the Domain resolver REQUIRES both
`postcode` and `state` to construct a valid slug. If either is missing,
`SuburbResolutionError` is raised.

Deep module — no HTTP calls. Uses the DB via the provided AsyncSession.
"""

import logging
from typing import ClassVar, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.db.models.suburb import Suburb
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

logger = logging.getLogger(__name__)


class SuburbResolutionError(Exception):
    """Raised when the Domain resolver cannot build a slug.

    This happens when postcode or state is not provided — both are
    required for the Domain slug format.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.suburb_name = name
        self.reason = reason
        super().__init__(f"Cannot resolve Domain suburb {name!r}: {reason}")


class DomainSuburbResolver:
    """Deterministic Domain suburb resolver: computes slug, caches in DB.

    Satisfies the VendorSuburbResolver protocol. Resolution is always
    consistent: given the same (name, postcode, state) the same slug is
    produced without any network call.

    The `source` class variable is used by the worker and service layers
    to dispatch to this resolver for Domain suburbs.
    """

    source: ClassVar[Vendor] = Vendor.DOMAIN

    async def resolve(
        self,
        name: str,
        *,
        db: AsyncSession,
        postcode: Optional[str] = None,
        state: Optional[str] = None,
    ) -> ResolvedSuburb:
        """Resolve a suburb name to a Domain ResolvedSuburb.

        Args:
            name: Suburb name, e.g. "Paddington".
            db: Async DB session for cache lookup and persistence.
            postcode: Required. The suburb's 4-digit postcode.
            state: Required. The suburb's state code, e.g. "QLD".

        Returns:
            A ResolvedSuburb with source=Vendor.DOMAIN and a Domain-format slug.

        Raises:
            SuburbResolutionError: If postcode or state is None — both are
                required to construct a valid Domain slug.
        """
        if not postcode or not state:
            raise SuburbResolutionError(
                name,
                "Domain resolver requires postcode and state to build a slug. "
                "Pass postcode= and state= (e.g. postcode='4064', state='QLD')."
            )

        slug = _build_slug(name, state, postcode)

        # Check cache: look for an existing row with matching source + name + postcode + state
        existing = await _lookup_cached(db, name, postcode=postcode, state=state)
        if existing is not None:
            logger.debug(
                "domain_resolver cache hit: %r/%s/%s → slug=%r",
                name, state, postcode, existing.slug,
            )
            return existing

        # Insert a new Suburb row for this Domain suburb
        row = Suburb(
            name=name.strip(),
            postcode=postcode.strip(),
            state=state.strip().upper(),
            slug=slug,
            source=Vendor.DOMAIN,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        logger.info(
            "domain_resolver: inserted suburb id=%d name=%r slug=%r",
            row.id, row.name, row.slug,
        )
        return ResolvedSuburb(
            id=row.id,
            name=row.name,
            postcode=row.postcode,
            state=row.state,
            source=Vendor.DOMAIN,
            slug=row.slug,
            resolved_at=row.resolved_at,
        )


async def _lookup_cached(
    session: AsyncSession,
    name: str,
    *,
    postcode: str,
    state: str,
) -> Optional[ResolvedSuburb]:
    """Return an existing Suburb row for this Domain suburb, or None."""
    stmt = (
        select(Suburb)
        .where(Suburb.source == Vendor.DOMAIN)
        .where(Suburb.name.ilike(name.strip()))
        .where(Suburb.postcode == postcode.strip())
        .where(Suburb.state == state.strip().upper())
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        return None
    return ResolvedSuburb(
        id=row.id,
        name=row.name,
        postcode=row.postcode,
        state=row.state,
        source=Vendor.DOMAIN,
        slug=row.slug,
        resolved_at=row.resolved_at,
    )


def _build_slug(name: str, state: str, postcode: str) -> str:
    """Build a Domain URL slug from suburb name, state, and postcode.

    Domain slug format: `<name-lowercased-hyphenated>-<state-lowercased>-<postcode>`
    Examples:
      "Paddington", "QLD", "4064" → "paddington-qld-4064"
      "Little Mountain", "QLD", "4551" → "little-mountain-qld-4551"
    """
    name_slug = name.strip().lower().replace(" ", "-")
    state_slug = state.strip().lower()
    postcode_clean = postcode.strip()
    return f"{name_slug}-{state_slug}-{postcode_clean}"
