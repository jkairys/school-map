"""Table-driven tests for price_normaliser.parser.

Tests are organised in three groups:
1. `normalise()` with OTH-style strings — covers all PriceKind branches.
2. `parse_oth_listing()` with OTH raw dict payloads — end-to-end extraction.
3. Edge cases: amounts below floor, empty string, None, two-amount ranges.
"""
import pytest

from listings_scraper.price_normaliser import NormalisedPrice, PriceKind, normalise, parse_oth_listing
from listings_scraper.vendor_clients.oth.types import Category


# ---------------------------------------------------------------------------
# normalise() — table-driven by spec
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "display,category,expected_kind,expected_low,expected_high",
    [
        # ForSale: single dollar amount
        ("$1,250,000", Category.FORSALE, PriceKind.PRICE, 1_250_000, None),
        # ForSale: range — two amounts
        ("$900,000 - $990,000", Category.FORSALE, PriceKind.RANGE, 900_000, 990_000),
        # ForSale: no amount, generic text → UNKNOWN
        ("For Sale", Category.FORSALE, PriceKind.UNKNOWN, None, None),
        # ForSale: "Contact agent" keyword → CONTACT
        ("Contact agent", Category.FORSALE, PriceKind.CONTACT, None, None),
        # ForSale: "Auction" keyword → AUCTION
        ("Auction", Category.FORSALE, PriceKind.AUCTION, None, None),
        # ForRent: dollar-per-week format
        ("$650/week", Category.FORRENT, PriceKind.RENT_WEEKLY, 650, None),
        # None input → UNKNOWN
        (None, Category.FORSALE, PriceKind.UNKNOWN, None, None),
        # Empty string → UNKNOWN
        ("", Category.FORSALE, PriceKind.UNKNOWN, None, None),
    ],
)
def test_normalise_table(
    display: str | None,
    category: Category,
    expected_kind: PriceKind,
    expected_low: int | None,
    expected_high: int | None,
) -> None:
    result = normalise(display, category)
    assert result.kind is expected_kind
    assert result.low == expected_low
    assert result.high == expected_high


def test_normalise_display_preserved() -> None:
    """The raw display string is always returned in .display."""
    raw = "$1,200,000"
    result = normalise(raw, Category.FORSALE)
    assert result.display == raw


def test_normalise_none_display_preserved() -> None:
    result = normalise(None, Category.FORSALE)
    assert result.display is None


# ---------------------------------------------------------------------------
# Additional branch coverage
# ---------------------------------------------------------------------------


def test_forsale_range_sorts_low_before_high() -> None:
    """If the display has the higher value first, low < high in output."""
    result = normalise("$990,000 - $900,000", Category.FORSALE)
    assert result.kind is PriceKind.RANGE
    assert result.low == 900_000
    assert result.high == 990_000


def test_forsale_amount_below_floor_yields_unknown() -> None:
    """An amount below _FORSALE_MIN_PRICE (100k) is treated as a parse artefact."""
    # "$2" matches the regex but is below the floor
    result = normalise("Inviting Offers in the Early $2m", Category.FORSALE)
    # "$2m" → "$2" (only 1 digit group, no comma) → below floor → UNKNOWN
    assert result.kind is PriceKind.UNKNOWN


def test_forsale_million_suffix_range_discarded_by_floor() -> None:
    """'$1.675mil - $1.75mil' regex-matches '$1' twice — both below floor → UNKNOWN."""
    result = normalise("$1.675mil - $1.75mil", Category.FORSALE)
    # The regex extracts [1, 1] (from '$1' prefix of each amount).
    # Both are below 100_000, so neither survives the floor filter → UNKNOWN.
    assert result.kind is PriceKind.UNKNOWN


def test_forsale_auction_case_insensitive() -> None:
    result = normalise("auction — contact agent for time", Category.FORSALE)
    assert result.kind is PriceKind.AUCTION


def test_forsale_eoi_keyword() -> None:
    result = normalise("Expressions of Interest", Category.FORSALE)
    assert result.kind is PriceKind.EOI


def test_forsale_eoi_short_form() -> None:
    result = normalise("EOI closing 30 May", Category.FORSALE)
    assert result.kind is PriceKind.EOI


def test_forrent_no_price_yields_contact() -> None:
    # "Same fallbacks as ForSale for non-numeric strings" (see module docstring).
    result = normalise("CONTACT AGENT", Category.FORRENT)
    assert result.kind is PriceKind.CONTACT


def test_forrent_contact_keyword() -> None:
    # "Same fallbacks as ForSale for non-numeric strings" (see module docstring).
    result = normalise("Contact landlord", Category.FORRENT)
    assert result.kind is PriceKind.CONTACT


def test_offers_over_price() -> None:
    result = normalise("Offers Over $1,485,000", Category.FORSALE)
    assert result.kind is PriceKind.PRICE
    assert result.low == 1_485_000


# ---------------------------------------------------------------------------
# parse_oth_listing() — OTH dict extraction
# ---------------------------------------------------------------------------


def _sale_raw(display_price: str | None = "For Sale") -> dict:
    return {
        "othPropertyId": "111",
        "listing": {"displayPrice": display_price},
    }


def _rent_raw(price: int | None = 700, display_price: str | None = "$700 per week") -> dict:
    return {
        "othPropertyId": "222",
        "listing": {"price": price, "displayPrice": display_price},
    }


def _sold_raw(sale_price: int | None = 1_500_000) -> dict:
    return {
        "othPropertyId": "333",
        "lastSale": {"salePrice": sale_price},
    }


def test_parse_oth_listing_forsale_with_dollar_amount() -> None:
    raw = _sale_raw("$1,250,000")
    result = parse_oth_listing(raw, Category.FORSALE)
    assert result.kind is PriceKind.PRICE
    assert result.low == 1_250_000
    assert result.high is None
    assert result.display == "$1,250,000"


def test_parse_oth_listing_forsale_no_amount() -> None:
    raw = _sale_raw("For Sale")
    result = parse_oth_listing(raw, Category.FORSALE)
    assert result.kind is PriceKind.UNKNOWN
    assert result.low is None


def test_parse_oth_listing_forsale_auction() -> None:
    raw = _sale_raw("Auction")
    result = parse_oth_listing(raw, Category.FORSALE)
    assert result.kind is PriceKind.AUCTION


def test_parse_oth_listing_forrent_with_price() -> None:
    raw = _rent_raw(price=650, display_price="$650 per week")
    result = parse_oth_listing(raw, Category.FORRENT)
    assert result.kind is PriceKind.RENT_WEEKLY
    assert result.low == 650


def test_parse_oth_listing_forrent_no_price_contact() -> None:
    raw = _rent_raw(price=None, display_price="CONTACT AGENT")
    result = parse_oth_listing(raw, Category.FORRENT)
    assert result.kind is PriceKind.CONTACT
    assert result.low is None


def test_parse_oth_listing_forrent_no_price_unknown() -> None:
    raw = _rent_raw(price=None, display_price="Inquire")
    result = parse_oth_listing(raw, Category.FORRENT)
    assert result.kind is PriceKind.UNKNOWN
    assert result.low is None


def test_parse_oth_listing_recentlysold_with_sale_price() -> None:
    raw = _sold_raw(sale_price=1_950_000)
    result = parse_oth_listing(raw, Category.RECENTLYSOLD)
    assert result.kind is PriceKind.PRICE
    assert result.low == 1_950_000
    assert result.display == "1950000"


def test_parse_oth_listing_recentlysold_no_sale_price() -> None:
    raw = _sold_raw(sale_price=None)
    result = parse_oth_listing(raw, Category.RECENTLYSOLD)
    assert result.kind is PriceKind.UNKNOWN
    assert result.low is None
    assert result.display is None


def test_parse_oth_listing_forsale_range() -> None:
    raw = _sale_raw("$900,000 - $990,000")
    result = parse_oth_listing(raw, Category.FORSALE)
    assert result.kind is PriceKind.RANGE
    assert result.low == 900_000
    assert result.high == 990_000
