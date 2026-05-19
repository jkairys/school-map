"""Backward-compat shim — exceptions moved to vendor_resolvers.oth.exceptions."""
from listings_scraper.vendor_resolvers.oth.exceptions import (  # noqa: F401
    AutocompleteUnavailableError,
    NoMatchError,
    ParseError,
)
