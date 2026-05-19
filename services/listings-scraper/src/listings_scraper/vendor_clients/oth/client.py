"""`OTHApiClient` — coordinates request build + HTTP call + parse.

The client owns no network state. The caller passes in a `ScrapeSession`
from which the client calls `await session.http()` to obtain the wrapped
httpx client. This indirection lets the session manage rotation, rate
limiting, and anti-bot detection transparently.

In tests the caller passes a fake `ScrapeSession` whose `http()` returns an
`httpx.AsyncClient` wired to an `httpx.MockTransport`. See
`tests/conftest.py` for `make_fake_scrape_session`.
"""

import logging
from typing import TYPE_CHECKING, Protocol

from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import SearchPage
from listings_scraper.vendor_clients.oth.parser import parse_search_response
from listings_scraper.vendor_clients.oth.payload import (
    DEFAULT_PAGE_SIZE,
    SEARCH_URL,
    build_search_payload,
)
from listings_scraper.vendor_clients.oth.types import (
    Category,
    ListingFilters,
)
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

if TYPE_CHECKING:
    import httpx

log = logging.getLogger(__name__)


class _ScrapeSessionLike(Protocol):
    """Minimal interface OTHApiClient needs from ScrapeSession.

    Defined locally to avoid a circular import between vendor_clients and
    scrape_session. The real ScrapeSession satisfies this Protocol.
    """

    async def http(self) -> "httpx.AsyncClient": ...


class OTHApiClient:
    """Issues paginated search requests against OTH and parses the response."""

    source: Vendor = Vendor.OTH

    def __init__(self, *, page_size: int = DEFAULT_PAGE_SIZE, timeout: float = 30.0) -> None:
        self._page_size = page_size
        self._timeout = timeout

    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,
        filters: ListingFilters,
        page: int,
        session: _ScrapeSessionLike,
    ) -> SearchPage:
        """Run one paginated search and return the parsed page.

        Raises `ParseError` (from `parse_search_response`) on a malformed body
        and propagates `httpx.HTTPStatusError` on non-2xx responses; the
        caller (worker loop) classifies those into transient vs anti-bot vs
        dead-letter outcomes.
        """
        payload = build_search_payload(
            suburb, category, filters, page, size=self._page_size
        )
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }

        log.debug(
            "OTH search: category=%s suburb=%s/%s page=%d",
            category.value,
            suburb.name,
            suburb.postcode,
            page,
        )
        http = await session.http()
        response = await http.post(
            SEARCH_URL, json=payload, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return parse_search_response(response.json(), category=category, page=page)
