"""`DomainApiClient` — browser-based Domain.com.au search client.

Domain renders its search results via Next.js server-side rendering. The
full listing data is embedded in a `__NEXT_DATA__` JSON blob in the HTML.
This client:

1. Obtains a camoufox Page from `session.page()`.
2. Navigates the Domain search URL for the requested suburb + category + page.
3. Reads `page.content()` to get the rendered HTML.
4. Extracts and parses `__NEXT_DATA__` via `extract_next_data` + `parse_next_data_listings`.
5. Checks Akamai anti-bot signals via the session's configured AntiBotDetector.

V1 limitation (URL filters):
  Domain URL filters (bedrooms, price range, property type) are path- and
  query-parameter-based. In v1 we do NOT encode filters in the URL — the
  client constructs a bare search URL and returns all listings from Domain's
  paginated feed. The worker stores all returned listings; downstream
  consumers can filter on the stored fields. A future PR will add URL-level
  filter encoding once the parameter shape is confirmed against the live
  Domain frontend.
  TODO(pr-after-3): add URL-level filter support for Domain searches.

Pagination:
  Domain uses 1-indexed pages in URLs. Our internal `page` argument is
  0-indexed. Domain returns paging info in componentProps.totalPages and
  componentProps.currentPage. We compare currentPage < totalPages to set
  has_next. If the listings list is empty, has_next is forced False.
"""

import logging
from datetime import datetime, timezone
from typing import ClassVar, Optional, Protocol

from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import SearchPage
from listings_scraper.vendor_clients.domain.exceptions import ParseError
from listings_scraper.vendor_clients.domain.next_data import extract_next_data
from listings_scraper.vendor_clients.domain.parser import parse_next_data_listings
from listings_scraper.vendor_resolvers.base import ResolvedSuburb

logger = logging.getLogger(__name__)

_DOMAIN_BASE_URL = "https://www.domain.com.au"

# Category value → Domain URL path segment
_CATEGORY_PATH: dict[str, str] = {
    "forsale": "sale",
    "forrent": "rent",
    "recentlysold": "sold",
}


class _ScrapeSessionLike(Protocol):
    """Minimal interface DomainApiClient needs from ScrapeSession."""

    async def page(self) -> object: ...  # Returns a camoufox AsyncPage


class DomainApiClient:
    """Issues paginated Domain search requests via a camoufox browser page.

    Uses `session.page()` (not `session.http()`) because Domain's search
    results are embedded in the Next.js HTML — there is no separate XHR
    endpoint for the listing data.
    """

    source: ClassVar[Vendor] = Vendor.DOMAIN

    async def search(
        self,
        suburb: ResolvedSuburb,
        category: object,  # Category from vendor_clients.oth.types
        filters: object,   # ListingFilters — not yet applied in v1
        page: int,         # 0-indexed
        session: _ScrapeSessionLike,
    ) -> SearchPage:
        """Fetch one page of Domain search results via a browser page.

        Args:
            suburb: The resolved suburb with a Domain-format slug
                (e.g. "paddington-qld-4064").
            category: The listing category (FORSALE / FORRENT / RECENTLYSOLD).
            filters: Filter criteria — NOT applied in v1 (see module docstring).
            page: 0-indexed page number. Converted to 1-indexed for the URL.
            session: A ScrapeSession configured with DOMAIN_CONFIG.

        Returns:
            A SearchPage with parsed VendorListing objects and the parallel
            raw listingModel dicts.

        Raises:
            ParseError: If the HTML or __NEXT_DATA__ cannot be parsed.
        """
        cat_str = category.value if hasattr(category, "value") else str(category)
        cat_path = _CATEGORY_PATH.get(cat_str)
        if cat_path is None:
            raise ParseError(f"Domain client: unknown category {cat_str!r}")

        slug = suburb.slug or ""
        # Domain pages are 1-indexed; our internal `page` is 0-indexed.
        domain_page = page + 1
        url = f"{_DOMAIN_BASE_URL}/{cat_path}/{slug}/?page={domain_page}"

        logger.info(
            "Domain search: category=%s suburb=%s/%s page=%d url=%s",
            cat_str,
            suburb.name,
            suburb.postcode,
            page,
            url,
        )

        browser_page = await session.page()
        try:
            await browser_page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            html = await browser_page.content()
        finally:
            await browser_page.close()

        observed_at = datetime.now(tz=timezone.utc)

        try:
            next_data = extract_next_data(html)
        except ParseError:
            logger.warning(
                "Domain search: could not extract __NEXT_DATA__ from page — "
                "possible anti-bot block or layout change. url=%s",
                url,
            )
            raise

        listings, raw_payloads = parse_next_data_listings(next_data, category, observed_at)

        # Pagination: compare currentPage < totalPages
        component_props = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("componentProps", {})
        )
        current_page: Optional[int] = _as_int_optional(component_props.get("currentPage"))
        total_pages: Optional[int] = _as_int_optional(component_props.get("totalPages"))

        has_next: bool
        if not listings:
            # Empty result page → stop paginating regardless of metadata
            has_next = False
        elif current_page is not None and total_pages is not None:
            has_next = current_page < total_pages
        else:
            # Missing pagination metadata — default to False (conservative)
            logger.warning(
                "Domain search: pagination metadata missing (currentPage=%r totalPages=%r) "
                "— defaulting has_next=False",
                current_page,
                total_pages,
            )
            has_next = False

        logger.info(
            "Domain search: parsed %d listings page=%d/%s has_next=%s",
            len(listings),
            page,
            total_pages,
            has_next,
        )

        return SearchPage(
            listings=listings,
            raw_payloads=raw_payloads,
            page=page,
            has_next=has_next,
            total=total_pages,
        )


def _as_int_optional(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
