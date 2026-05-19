"""Value objects for the price_normaliser module.

Deep module — no I/O, no DB, no logger calls.
"""
from dataclasses import dataclass

from listings_scraper.vendor_clients.base import PriceKind


@dataclass(frozen=True)
class NormalisedPrice:
    """The vendor-neutral result of parsing a price string.

    `low` is the primary numeric value (asking price, rent, range lower bound).
    `high` is only set for range prices (e.g. "$900,000 - $990,000").
    `display` is the original raw string as-received from the vendor.
    """

    kind: PriceKind
    low: int | None
    high: int | None
    display: str | None
