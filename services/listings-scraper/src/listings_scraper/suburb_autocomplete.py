"""Suburb autocomplete — read-only wrapper around OTH's autocomplete endpoint.

Deep module. Returns `Match[]` verbatim from OTH. Does NOT persist anything;
the existing `suburb_resolver.resolve` is the sole writer.

Distinction from `suburb_resolver`:
- `suburb_resolver.resolve` → disambiguates + caches to DB (writer).
- `suburb_autocomplete.autocomplete` → raw candidate list, no DB (reader).

Empty `q` returns an empty list (no network call).
OTH errors are re-raised as `AutocompleteUnavailableError` (matching the
error contract callers already handle via `suburb_resolver`).
"""

import httpx

from listings_scraper.suburb_resolver import AutocompleteUnavailableError, Match
from listings_scraper.vendor_resolvers.oth.resolver import _fetch_autocomplete  # noqa: PLC2701


async def autocomplete(
    q: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[Match]:
    """Return OTH autocomplete candidates for query string `q`.

    Args:
        q: Free-text search string. Empty/blank → returns [] immediately.
        client: Optional httpx client (for testing). A fresh client is created
                and closed when not provided.

    Returns:
        List of `Match` objects (suburb-level only). May be empty when OTH
        returns no suburb-level rows. NOT filtered by name equality — every
        suburb-level candidate from OTH is returned verbatim.

    Raises:
        AutocompleteUnavailableError: OTH endpoint unreachable, anti-bot
            blocked, or any HTTP error response from OTH.
    """
    cleaned = q.strip()
    if not cleaned:
        return []

    try:
        # Re-use the same low-level HTTP + parse logic from suburb_resolver so
        # the two never diverge on request shape or response parsing.
        return await _fetch_autocomplete(cleaned, client=client)
    except httpx.HTTPStatusError as e:
        # _fetch_autocomplete only converts 401/403/429 to AutocompleteUnavailableError;
        # other HTTP error codes (e.g. 500, 503) raise httpx.HTTPStatusError.
        # Normalise all of them to AutocompleteUnavailableError so callers have
        # one error type to handle.
        raise AutocompleteUnavailableError(
            f"OTH autocomplete returned HTTP {e.response.status_code}"
        ) from e
