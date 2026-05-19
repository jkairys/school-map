"""OTH suburb resolver — turn a free-text suburb name into a ResolvedSuburb.

Deep module. Hits OTH's `/odin/api/locations` autocomplete endpoint, parses
suburb-level candidates, and caches single confident matches in the `suburb`
table. See PR for issue 02 for the captured request/response shapes.
"""

import logging
from typing import Any, ClassVar, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.db.models.suburb import Suburb
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_resolvers.base import Match, ResolvedSuburb
from listings_scraper.vendor_resolvers.oth.exceptions import (
    AutocompleteUnavailableError,
    NoMatchError,
    ParseError,
)

logger = logging.getLogger(__name__)

AUTOCOMPLETE_URL = "https://www.onthehouse.com.au/odin/api/locations"


class OTHSuburbResolver:
    """Protocol-conformant wrapper around the module-level `resolve()` function.

    Satisfies `VendorSuburbResolver` so PR 3 can dispatch to OTH and Domain
    resolvers polymorphically. The module-level `resolve()` is preserved for
    backward-compat with the `suburb_resolver/` shim.
    """

    source: ClassVar[Vendor] = Vendor.OTH

    async def resolve(
        self,
        name: str,
        *,
        db: AsyncSession,
        postcode: Optional[str] = None,
        state: Optional[str] = None,
    ) -> "ResolvedSuburb | list[Match]":
        return await resolve(name, session=db, postcode=postcode, state=state)
DEFAULT_HEADERS: dict[str, str] = {
    "accept": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "referer": "https://www.onthehouse.com.au/",
}


async def resolve(
    name: str,
    *,
    session: AsyncSession,
    client: httpx.AsyncClient | None = None,
    postcode: str | None = None,
    state: str | None = None,
) -> ResolvedSuburb | list[Match]:
    """Resolve a free-text suburb name to a ResolvedSuburb or list of candidates.

    Resolution order:
    1. If `postcode` and/or `state` filters narrow the cache to exactly one
       row (case-insensitive name match), return it without hitting OTH.
    2. Query OTH `/odin/api/locations`, filter to suburb-level rows whose
       suburb name equals `name` case-insensitively, then apply optional
       `postcode`/`state` filters.
    3. Single match → upsert into `suburb`, return ResolvedSuburb.
       Multiple matches → return list[Match].
       Zero matches → raise NoMatchError.

    Args:
        name: Free-text suburb name (e.g. "Little Mountain").
        session: Async DB session for cache lookups + persistence.
        client: Optional httpx client (lets tests inject mocks).
        postcode: Optional disambiguation filter.
        state: Optional disambiguation filter (e.g. "QLD").
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("name must be non-empty")

    cached = await _lookup_cached(session, cleaned, postcode=postcode, state=state)
    if cached is not None:
        logger.debug("suburb_resolver cache hit for %r → %s", cleaned, cached.slug)
        return cached

    matches = await _fetch_autocomplete(cleaned, client=client)
    matches = _filter_matches(matches, cleaned, postcode=postcode, state=state)

    if not matches:
        raise NoMatchError(f"OTH autocomplete returned no suburb matches for {cleaned!r}")

    if len(matches) == 1:
        return await _upsert(session, matches[0])

    return matches


async def _lookup_cached(
    session: AsyncSession,
    name: str,
    *,
    postcode: str | None,
    state: str | None,
) -> ResolvedSuburb | None:
    stmt = select(Suburb).where(Suburb.name.ilike(name))
    if postcode is not None:
        stmt = stmt.where(Suburb.postcode == postcode)
    if state is not None:
        stmt = stmt.where(Suburb.state == state.upper())
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) == 1:
        row = rows[0]
        return ResolvedSuburb(
            id=row.id,
            name=row.name,
            postcode=row.postcode,
            state=row.state,
            source=Vendor.OTH,
            slug=row.oth_slug,
            resolved_at=row.resolved_at,
        )
    return None


async def _upsert(session: AsyncSession, match: Match) -> ResolvedSuburb:
    stmt = select(Suburb).where(
        Suburb.name == match.name,
        Suburb.postcode == match.postcode,
        Suburb.state == match.state,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return ResolvedSuburb(
            id=existing.id,
            name=existing.name,
            postcode=existing.postcode,
            state=existing.state,
            source=Vendor.OTH,
            slug=existing.oth_slug,
            resolved_at=existing.resolved_at,
        )

    row = Suburb(
        name=match.name,
        postcode=match.postcode,
        state=match.state,
        oth_slug=match.slug or _build_slug(match.name, match.postcode),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ResolvedSuburb(
        id=row.id,
        name=row.name,
        postcode=row.postcode,
        state=row.state,
        source=Vendor.OTH,
        slug=row.oth_slug,
        resolved_at=row.resolved_at,
    )


async def _fetch_autocomplete(
    name: str, *, client: httpx.AsyncClient | None
) -> list[Match]:
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
    try:
        try:
            response = await client.get(
                AUTOCOMPLETE_URL,
                params={"query": name},
                headers=DEFAULT_HEADERS,
            )
        except httpx.HTTPError as e:
            raise AutocompleteUnavailableError(
                f"OTH autocomplete request failed: {e}"
            ) from e

        if response.status_code in (401, 403, 429):
            # Empirical finding (issue 02 PR): bare httpx works without cookies.
            # If this changes, the resolver needs to run inside the camoufox
            # session (issue 10) — convert this issue to Blocked by 10.
            raise AutocompleteUnavailableError(
                f"OTH autocomplete returned {response.status_code} — likely anti-bot."
            )
        response.raise_for_status()
        return _parse_response(response.json())
    finally:
        if owns_client:
            await client.aclose()


def _parse_response(payload: Any) -> list[Match]:
    """Parse `/odin/api/locations` response into suburb-level Match objects.

    Filters out street-level (`streetName` present) and address-level
    (`streetNumber` non-empty) rows. Only suburb-level rows become Matches.
    """
    if not isinstance(payload, dict) or "content" not in payload:
        raise ParseError("OTH autocomplete payload missing 'content' array")
    content = payload["content"]
    if not isinstance(content, list):
        raise ParseError("OTH autocomplete 'content' is not a list")

    matches: list[Match] = []
    for row in content:
        if not isinstance(row, dict):
            continue
        if row.get("streetNumber"):
            continue
        if "streetName" in row:
            continue
        try:
            suburb = row["suburb"]
            postcode = row["postCode"]
            state = row["stateCode"]
        except KeyError as e:
            raise ParseError(f"OTH autocomplete row missing field: {e}") from e
        matches.append(
            Match(
                name=suburb,
                postcode=postcode,
                state=state,
                source=Vendor.OTH,
                slug=_build_slug(suburb, postcode),
            )
        )
    return matches


def _filter_matches(
    matches: list[Match],
    name: str,
    *,
    postcode: str | None,
    state: str | None,
) -> list[Match]:
    target = name.casefold()
    out = [m for m in matches if m.name.casefold() == target]
    if postcode is not None:
        out = [m for m in out if m.postcode == postcode]
    if state is not None:
        out = [m for m in out if m.state == state.upper()]
    return out


def _build_slug(suburb: str, postcode: str) -> str:
    return f"{suburb.lower().replace(' ', '-')}-{postcode}"
