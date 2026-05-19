"""OTH (onthehouse.com.au) suburb resolver."""

from listings_scraper.vendor_resolvers.oth.resolver import OTHSuburbResolver, resolve
from listings_scraper.vendor_resolvers.oth.exceptions import (
    AutocompleteUnavailableError,
    NoMatchError,
    ParseError,
)

__all__ = [
    "OTHSuburbResolver",
    "resolve",
    "AutocompleteUnavailableError",
    "NoMatchError",
    "ParseError",
]
