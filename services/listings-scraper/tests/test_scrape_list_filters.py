"""Unit tests for the ScrapeListFilters Pydantic validator.

DB-free: only exercises the on-write validation rules. Acceptance criterion
explicitly: unknown keys, negatives, inverted ranges → 422.
"""
import pytest
from pydantic import ValidationError

from listings_scraper.services.scrape_list import ScrapeListFilters


def test_empty_is_valid_all_none():
    f = ScrapeListFilters()
    assert f.beds_min is None
    assert f.beds_max is None
    assert f.property_types is None
    assert f.price_min is None
    assert f.price_max is None


def test_full_payload_round_trips():
    f = ScrapeListFilters.model_validate(
        {
            "beds_min": 3,
            "beds_max": 4,
            "property_types": ["House", "Townhouse"],
            "price_min": 500_000,
            "price_max": 1_500_000,
        }
    )
    assert f.beds_min == 3
    assert f.beds_max == 4
    assert f.property_types == ["House", "Townhouse"]


@pytest.mark.parametrize("payload", [
    {"bathrooms_min": 2},
    {"beds_min": 3, "extra": "nope"},
])
def test_unknown_key_rejected(payload):
    with pytest.raises(ValidationError):
        ScrapeListFilters.model_validate(payload)


@pytest.mark.parametrize("payload", [
    {"beds_min": -1},
    {"beds_max": -3},
    {"price_min": -100},
    {"price_max": -500},
])
def test_negative_numbers_rejected(payload):
    with pytest.raises(ValidationError):
        ScrapeListFilters.model_validate(payload)


def test_inverted_beds_range_rejected():
    with pytest.raises(ValidationError):
        ScrapeListFilters.model_validate({"beds_min": 5, "beds_max": 2})


def test_inverted_price_range_rejected():
    with pytest.raises(ValidationError):
        ScrapeListFilters.model_validate(
            {"price_min": 2_000_000, "price_max": 1_000_000}
        )


def test_equal_min_max_allowed():
    """beds_min == beds_max is fine — it's a single-value query."""
    f = ScrapeListFilters.model_validate(
        {"beds_min": 3, "beds_max": 3, "price_min": 500, "price_max": 500}
    )
    assert f.beds_min == f.beds_max == 3
