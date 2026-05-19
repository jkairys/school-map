"""Price parsing for OTH and Domain (and future vendors).

Deep module — no I/O, no DB, no logger calls. Input: raw vendor string +
category. Output: NormalisedPrice value object.

The public entry point `normalise()` classifies a free-form display string.
It was previously named `_classify_oth` internally; the rename to
`_classify_freeform` reflects that the logic is substantially generic
and is now called from both OTH and Domain paths.

OTH-specific rules (via `parse_oth_listing`)
---------------------------------------------
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

Domain-specific rules (via `parse_domain_listing`)
---------------------------------------------------
Domain's `price` field is a free-form display string. Observed varieties
from the spike fixture:
  - "$1,250,000" (clean amount)
  - "For Sale", "Auction", "EOI", "Contact Agent"
  - "Offers over $3,300,000", "Offers above $X", "From $X"
  - "Price Guide $12M $12.5M", "Guide $850k-$900k"
  - "BEST OFFERS closing 26th May at 3.00pm"
  - "$650 per week" for rentals
  - "THE DEAL: Expressions of Interest"

Mapping rules mirror the OTH freeform classifier with:
  - M/k suffixes for million/thousand (e.g. "$12M", "$850k")
  - "Offers over" / "OFFERS OVER" / "from" with one numeric → PRICE(low=N)
    (we treat "offers over" as a price floor — slightly lossy but better
    than UNKNOWN; the raw display string is always stored verbatim)
  - Two numerics → RANGE(low=A, high=B)

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

# A standard dollar amount with comma-separated thousands (≥ 1 digit group).
# Matches "$1,485,000" or "$650" (3-digit or fewer as standalone amount).
_DOLLAR_AMOUNT_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d{1,3})")

# Dollar amounts with M (million) or k/K (thousand) suffix.
# Matches "$12M", "$12.5M", "$850k", "$1.2m".
# The decimal part is optional. Case-insensitive suffix.
_DOLLAR_SUFFIX_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*([MmKk])\b")

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
    return _classify_freeform(display, category)


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
        return _classify_freeform(display, category)

    # FORSALE: free-text displayPrice
    display_raw = listing.get("displayPrice")
    display = display_raw if isinstance(display_raw, str) and display_raw else None
    return _classify_freeform(display, category)


def parse_domain_listing(raw: dict, category: "Category") -> NormalisedPrice:
    """Domain-specific helper: parse a Domain listingModel price field.

    Domain's `price` field is a free-form display string. This function
    extracts it, handles M/k suffixes for large amounts, and delegates to
    the shared `_classify_freeform()` classifier.

    Observed Domain price string varieties (from spike fixture):
      - "$1,250,000" → PRICE(1250000)
      - "For Sale" → UNKNOWN
      - "Auction" → AUCTION
      - "EOI" / "Expressions of Interest" → EOI
      - "Contact Agent" → CONTACT
      - "Offers over $3,300,000" → PRICE(3300000)
      - "OFFERS OVER $845,000" → PRICE(845000)
      - "Price Guide $12M $12.5M" → RANGE(12000000, 12500000)
      - "$650 per week" (FORRENT) → RENT_WEEKLY(650)
      - "BEST OFFERS closing 26th May at 3.00pm" → UNKNOWN
      - "UNDER CONTRACT" → UNKNOWN (status carried in tags, not price)

    Args:
        raw: A Domain `listingModel` dict (the value in listingsMap[id]).
        category: The listing category.

    Returns:
        A NormalisedPrice.
    """
    display: Optional[str] = raw.get("price") or None
    if not display:
        return NormalisedPrice(kind=PriceKind.UNKNOWN, low=None, high=None, display=display)

    # Attempt to extract M/k suffix amounts (e.g. $12M, $12.5M, $850k).
    # These take precedence over plain _DOLLAR_AMOUNT_RE since the dollar-
    # only regex would extract just "$12" (→ 12, below floor) and miss the suffix.
    suffix_amounts = _extract_suffix_amounts(display)

    cat = category.value if hasattr(category, "value") else str(category)
    if suffix_amounts:
        if cat == "forrent":
            return NormalisedPrice(
                kind=PriceKind.RENT_WEEKLY, low=suffix_amounts[0], high=None, display=display
            )
        # ForSale / RecentlySold
        valid = [a for a in suffix_amounts if a >= _FORSALE_MIN_PRICE]
        if len(valid) >= 2:
            low, high = sorted(valid[:2])
            return NormalisedPrice(kind=PriceKind.RANGE, low=low, high=high, display=display)
        if len(valid) == 1:
            return NormalisedPrice(kind=PriceKind.PRICE, low=valid[0], high=None, display=display)

    # Fall through to the shared freeform classifier which handles plain $ amounts
    # and all keyword patterns (Auction, EOI, Contact, Offers over, etc.)
    return _classify_freeform(display, category)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_freeform(display: Optional[str], category: "Category") -> NormalisedPrice:
    """Classify a free-form price display string for ForSale or ForRent.

    Previously named `_classify_oth`; renamed to `_classify_freeform` in PR 3
    to reflect that this logic is vendor-neutral and used from both OTH and
    Domain paths. The logic is unchanged.
    """
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
    """Extract all plain dollar amounts from a display string, in order of appearance."""
    return [int(m.group(1).replace(",", "")) for m in _DOLLAR_AMOUNT_RE.finditer(display)]


def _extract_suffix_amounts(display: str) -> list[int]:
    """Extract dollar amounts with M (million) or k/K (thousand) suffix.

    Returns amounts in order of appearance. Only matched if a suffix is
    present — plain $ amounts without suffixes are handled by _extract_amounts.

    Examples:
      "$12M"    → [12_000_000]
      "$12.5M"  → [12_500_000]
      "$850k"   → [850_000]
      "$1.2m"   → [1_200_000]
    """
    results: list[int] = []
    for m in _DOLLAR_SUFFIX_RE.finditer(display):
        numeric_str = m.group(1)
        suffix = m.group(2).upper()
        try:
            value = float(numeric_str)
        except ValueError:
            continue
        if suffix == "M":
            results.append(int(value * 1_000_000))
        elif suffix == "K":
            results.append(int(value * 1_000))
    return results


def _as_int_optional(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
