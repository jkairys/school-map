"""Backward-compat shim — `suburb_resolver` moved to `vendor_resolvers.oth`.

This shim re-exports the public surface so existing code that imports from
`listings_scraper.suburb_resolver` continues to work during PR 1. PR 3
will clean up these aliases.
"""

from listings_scraper.vendor_resolvers.oth.exceptions import (
    AutocompleteUnavailableError,
    NoMatchError,
    ParseError,
)
from listings_scraper.vendor_resolvers.base import Match, ResolvedSuburb
from listings_scraper.vendor_resolvers.oth.resolver import resolve

__all__ = [
    "AutocompleteUnavailableError",
    "Match",
    "NoMatchError",
    "ParseError",
    "ResolvedSuburb",
    "resolve",
]
