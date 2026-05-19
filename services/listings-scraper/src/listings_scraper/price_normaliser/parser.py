"""Price parsing for OTH (and future vendors).

Deep module — no I/O, no DB, no logger calls. Input: raw vendor string +
category. Output: NormalisedPrice value object.

OTH-specific rules
------------------
ForSale / RecentlySold:
  - One dollar amount  →  PRICE (low=N, high=None)
  - Two dollar amounts →  RANGE (low=A, high=B, A < B)
  - No amount, "Auction" in string  →  AUCTION
  - No amount, "EOI" / "expressions of interest"  →  EOI
  - No amount, "Contact" in string or empty/None  →  CONTACT
  - Otherwise  →  UNKNOWN

ForRent:
  - One dollar amount  →  RENT_WEEKLY (low=N, high=None)
  - Same fallbacks as ForSale for non-numeric strings

Price floor: any parsed amount below _FORSALE_MIN_PRICE is discarded as a
parse artefact (e.g. "Early $2m" regex-matches "$2" → 2). Rental listings
are exempt from the floor check since $300/week is valid.

Import note: `Category` is imported lazily inside function bodies to avoid a
circular import between `price_normaliser` and `vendor_clients.oth` (each of
which depends on the other during package initialisation).
"""
import re
from typing import TYPE_CHECKING, Any, Optional

from listings_scraper.vendor_clients.base import PriceKind

from .types import NormalisedPrice

if TYPE_CHECKING:
    from listings_scraper.vendor_clients.oth.types import Category

# A dollar amount with at least one comma-separated thousands group (≥ 1000).
# Matches "$1,485,000" or "$650" (where the 3-digit group is the full amount).
_DOLLAR_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d{1,3})")

# Minimum price for ForSale/RecentlySold. Below this we treat the parse as
# a noise artefact and discard the number.
_FORSALE_MIN_PRICE = 100_000


def normalise(display: Optional[str], category: "Category") -> NormalisedPrice:
    """Top-level pure function: classify a vendor display string by category.

    Args:
        display: The raw price display string from the vendor API. May be None
            or empty.
        category: The listing category to apply vendor-specific rules.

    Returns:
        A NormalisedPrice describing the kind and parsed value(s).
    """
    return _classify_oth(display, category)


def parse_oth_listing(raw: dict, category: "Category") -> NormalisedPrice:
    """OTH-specific helper: extract the display string and normalise.

    Pulls the price string from the appropriate OTH JSON field for the
    category and delegates to `normalise()`.

    For RECENTLYSOLD we use `lastSale.salePrice` (integer) directly.
    For FORRENT and FORSALE we read `listing.displayPrice`.
    """
    # Category is str,Enum — compare via .value (or getattr fallback for plain
    # strings) to avoid importing it at module level (circular import).
    cat = category.value if hasattr(category, "value") else str(category)
    if cat == "recentlysold":
        last_sale = raw.get("lastSale") or {}
        price = _as_int_optional(last_sale.get("salePrice"))
        display = str(price) if price is not None else None
        kind = PriceKind.PRICE if price is not None else PriceKind.UNKNOWN
        return NormalisedPrice(kind=kind, low=price, high=None, display=display)

    listing = raw.get("listing") or {}

    if cat == "forrent":
        # OTH gives a clean integer weekly rent on rental listings.
        price = _as_int_optional(listing.get("price"))
        display_raw = listing.get("displayPrice")
        display = display_raw if isinstance(display_raw, str) and display_raw else (
            str(price) if price is not None else None
        )
        if price is not None:
            return NormalisedPrice(kind=PriceKind.RENT_WEEKLY, low=price, high=None, display=display)
        # price is None — fall through to keyword classifier (CONTACT / AUCTION / EOI / UNKNOWN)
        return _classify_oth(display, category)

    # FORSALE: free-text displayPrice
    display_raw = listing.get("displayPrice")
    display = display_raw if isinstance(display_raw, str) and display_raw else None
    return _classify_oth(display, category)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_oth(display: Optional[str], category: "Category") -> NormalisedPrice:
    """Classify an OTH display price string for ForSale or ForRent categories."""
    if not display:
        return NormalisedPrice(kind=PriceKind.UNKNOWN, low=None, high=None, display=display)

    amounts = _extract_amounts(display)

    cat = category.value if hasattr(category, "value") else str(category)
    if cat == "forrent":
        if amounts:
            return NormalisedPrice(
                kind=PriceKind.RENT_WEEKLY, low=amounts[0], high=None, display=display
            )
    else:
        # ForSale / RecentlySold — apply floor to discard regex artefacts like
        # "$1" extracted from "$1.675mil" before the suffix is consumed.
        valid = [a for a in amounts if a >= _FORSALE_MIN_PRICE]
        if len(valid) >= 2:
            low, high = sorted(valid[:2])
            return NormalisedPrice(kind=PriceKind.RANGE, low=low, high=high, display=display)
        if len(valid) == 1:
            return NormalisedPrice(
                kind=PriceKind.PRICE, low=valid[0], high=None, display=display
            )

    # No valid dollar amount — classify by keywords
    upper = display.upper()
    if "AUCTION" in upper:
        return NormalisedPrice(kind=PriceKind.AUCTION, low=None, high=None, display=display)
    if "EOI" in upper or "EXPRESSION" in upper:
        return NormalisedPrice(kind=PriceKind.EOI, low=None, high=None, display=display)
    if "CONTACT" in upper:
        return NormalisedPrice(kind=PriceKind.CONTACT, low=None, high=None, display=display)

    return NormalisedPrice(kind=PriceKind.UNKNOWN, low=None, high=None, display=display)


def _extract_amounts(display: str) -> list[int]:
    """Extract all dollar amounts from a display string, in order of appearance."""
    return [int(m.group(1).replace(",", "")) for m in _DOLLAR_AMOUNT_RE.finditer(display)]


def _as_int_optional(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
