"""`OTHApiClient` — coordinates request build + HTTP call + parse.

The client owns no network state. The caller passes in an `httpx.AsyncClient`
that has been pre-configured with whatever cookies/headers the upstream
anti-bot bootstrap (issue 10's `scrape_session`) captured. In tests the
caller passes a `pytest-httpx`-style mocked client.
"""

import logging
from typing import Optional

import httpx

from oth_scraper.oth_client.parser import parse_search_response
from oth_scraper.oth_client.payload import (
    DEFAULT_PAGE_SIZE,
    SEARCH_URL,
    build_search_payload,
)
from oth_scraper.oth_client.types import (
    Category,
    ListingFilters,
    ResolvedSuburb,
    SearchPage,
)

log = logging.getLogger(__name__)


class OTHApiClient:
    """Issues paginated search requests against OTH and parses the response."""

    def __init__(self, *, page_size: int = DEFAULT_PAGE_SIZE, timeout: float = 30.0) -> None:
        self._page_size = page_size
        self._timeout = timeout

    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,
        filters: ListingFilters,
        page: int,
        http: httpx.AsyncClient,
        *,
        extra_headers: Optional[dict[str, str]] = None,
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
        if extra_headers:
            headers.update(extra_headers)

        log.debug(
            "OTH search: category=%s suburb=%s/%s page=%d",
            category.value,
            suburb.name,
            suburb.postcode,
            page,
        )
        response = await http.post(
            SEARCH_URL, json=payload, headers=headers, timeout=self._timeout
        )
        response.raise_for_status()
        return parse_search_response(response.json(), category=category, page=page)
