"""Backward-compat shim — payload module moved to vendor_clients.oth.payload."""
from listings_scraper.vendor_clients.oth.payload import (  # noqa: F401
    DEFAULT_PAGE_SIZE,
    SEARCH_URL,
    build_search_payload,
)
