"""Snapshot tests for the OTH search-API request builder.

The expected payloads under `tests/fixtures/expected_payloads/` are the
contract: when filters change in shape, regenerate them deliberately
(see `scripts/capture_fixtures.py` and the docstring on parser.py for how
this fixture set was produced) — never silently update them to make a test
pass.
"""

import json
from pathlib import Path

import pytest

from oth_scraper.oth_client import (
    Category,
    ListingFilters,
    PropertyType,
    ResolvedSuburb,
)
from oth_scraper.oth_client.payload import build_search_payload


PADDINGTON = ResolvedSuburb(name="Paddington", state="QLD", postcode="4064")


def _load(expected_payloads_dir: Path, name: str) -> dict:
    return json.loads((expected_payloads_dir / f"{name}.json").read_text())


SNAPSHOTS = [
    pytest.param(
        "forsale_unfiltered", Category.FORSALE, ListingFilters(), 0, id="forsale-unfiltered"
    ),
    pytest.param(
        "forrent_unfiltered", Category.FORRENT, ListingFilters(), 0, id="forrent-unfiltered"
    ),
    pytest.param(
        "recentlysold_unfiltered",
        Category.RECENTLYSOLD,
        ListingFilters(),
        0,
        id="recentlysold-unfiltered",
    ),
    pytest.param(
        "forsale_filtered",
        Category.FORSALE,
        ListingFilters(
            beds_min=3,
            beds_max=4,
            property_types=(PropertyType.HOUSE, PropertyType.TOWNHOUSE),
            price_min=1_000_000,
            price_max=2_000_000,
        ),
        1,
        id="forsale-filtered",
    ),
    pytest.param(
        "forrent_filtered",
        Category.FORRENT,
        ListingFilters(
            beds_min=2,
            property_types=(PropertyType.APARTMENT,),
            price_min=400,
            price_max=800,
        ),
        0,
        id="forrent-filtered",
    ),
    pytest.param(
        "recentlysold_filtered",
        Category.RECENTLYSOLD,
        ListingFilters(
            beds_min=3,
            beds_max=4,
            property_types=(PropertyType.HOUSE,),
            price_max=2_500_000,
        ),
        0,
        id="recentlysold-filtered",
    ),
]


@pytest.mark.parametrize("snapshot_name,category,filters,page", SNAPSHOTS)
def test_build_search_payload_matches_snapshot(
    expected_payloads_dir: Path,
    snapshot_name: str,
    category: Category,
    filters: ListingFilters,
    page: int,
) -> None:
    expected = _load(expected_payloads_dir, snapshot_name)
    actual = build_search_payload(PADDINGTON, category, filters, page)
    assert actual == expected


def test_filter_price_field_routes_per_category() -> None:
    """Each category routes the price filter into a different JSON key.

    SaleListing and RecentlySold share ``priceMin``/``priceMax``;
    RentalListing diverges to ``forRentPriceMin``/``forRentPriceMax``.
    All filter keys live inside ``query.queries[0]`` (the per-suburb
    target), not under ``query`` — captured live from the OTH frontend.
    """
    f = ListingFilters(price_min=500_000, price_max=1_000_000)
    sale = build_search_payload(PADDINGTON, Category.FORSALE, f, 0)
    rent = build_search_payload(PADDINGTON, Category.FORRENT, f, 0)
    sold = build_search_payload(PADDINGTON, Category.RECENTLYSOLD, f, 0)

    assert "priceMin" in sale["query"]["queries"][0]
    assert "priceMax" in sale["query"]["queries"][0]
    assert "forRentPriceMin" in rent["query"]["queries"][0]
    assert "forRentPriceMax" in rent["query"]["queries"][0]
    assert "priceMin" in sold["query"]["queries"][0]
    assert "priceMax" in sold["query"]["queries"][0]
    # Price keys must NOT appear at the query level — that shape 400s.
    assert "priceMin" not in sale["query"]
    assert "forRentPriceMin" not in rent["query"]


def test_recentlysold_omits_status_current() -> None:
    """RecentlySold queries must not carry status:'current' — that's a
    live-listing discriminator that 400s the request when sent on a sold
    query."""
    payload = build_search_payload(PADDINGTON, Category.RECENTLYSOLD, ListingFilters(), 0)
    target = payload["query"]["queries"][0]
    assert "status" not in target


def test_forsale_and_forrent_carry_status_current() -> None:
    for cat in (Category.FORSALE, Category.FORRENT):
        payload = build_search_payload(PADDINGTON, cat, ListingFilters(), 0)
        target = payload["query"]["queries"][0]
        assert target.get("status") == "current"


def test_unfiltered_payload_has_no_filter_keys() -> None:
    payload = build_search_payload(PADDINGTON, Category.FORSALE, ListingFilters(), 0)
    # No extra keys under `query` (only `queries`).
    assert set(payload["query"]) == {"queries"}
    # And the target object only carries the suburb/category descriptor.
    target = payload["query"]["queries"][0]
    expected = {"category", "stateCode", "suburb", "postCode", "status"}
    assert set(target) == expected


def test_state_is_uppercased() -> None:
    suburb = ResolvedSuburb(name="Bondi", state="nsw", postcode="2026")
    payload = build_search_payload(suburb, Category.FORSALE, ListingFilters(), 0)
    assert payload["query"]["queries"][0]["stateCode"] == "NSW"


def test_suburb_name_is_lowercased() -> None:
    suburb = ResolvedSuburb(name="Wynnum West", state="QLD", postcode="4178")
    payload = build_search_payload(suburb, Category.FORSALE, ListingFilters(), 0)
    assert payload["query"]["queries"][0]["suburb"] == "wynnum west"


def test_pagination_carries_through() -> None:
    payload = build_search_payload(PADDINGTON, Category.FORSALE, ListingFilters(), 5)
    assert payload["number"] == 5
    assert payload["size"] == 24


def test_custom_page_size() -> None:
    payload = build_search_payload(PADDINGTON, Category.FORSALE, ListingFilters(), 0, size=100)
    assert payload["size"] == 100
