"""price_normaliser — vendor-neutral price string classification.

Deep module: no I/O, no DB, no logger calls.

Re-exports the public surface:
- `normalise`: top-level pure function (display string + category → NormalisedPrice)
- `parse_oth_listing`: OTH-specific helper (raw dict + category → NormalisedPrice)
- `NormalisedPrice`: the value object
- `PriceKind`: the enum (re-exported from vendor_clients.base for convenience)
"""
from listings_scraper.vendor_clients.base import PriceKind

from .parser import normalise, parse_oth_listing
from .types import NormalisedPrice

__all__ = ["NormalisedPrice", "PriceKind", "normalise", "parse_oth_listing"]
