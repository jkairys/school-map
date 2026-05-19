"""OTH-specific suburb models — shim pointing to vendor_resolvers.base.

The canonical `ResolvedSuburb` and `Match` models now live in
`listings_scraper.vendor_resolvers.base` (vendor-neutral). This module
re-exports them so existing code that imported from the old
`suburb_resolver.models` path (now `vendor_resolvers.oth.models`) continues
to work during PR 1. PR 3 will clean up these aliases.
"""

from listings_scraper.vendor_resolvers.base import Match, ResolvedSuburb

__all__ = ["Match", "ResolvedSuburb"]
