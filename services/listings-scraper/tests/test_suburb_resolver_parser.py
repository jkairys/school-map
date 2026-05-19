"""Pure-parser tests for suburb_resolver — no HTTP, no DB."""

import json
from pathlib import Path

import pytest

from listings_scraper.suburb_resolver.exceptions import ParseError
from listings_scraper.suburb_resolver.resolver import (
    _build_slug,
    _filter_matches,
    _parse_response,
)

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_parse_filters_street_and_address_rows():
    matches = _parse_response(_load("little_mountain.json"))
    # Fixture has 1 suburb-level + 3 street-level + 6 address-level rows.
    assert len(matches) == 1
    m = matches[0]
    assert m.name == "LITTLE MOUNTAIN"
    assert m.state == "QLD"
    assert m.postcode == "4551"
    assert m.slug == "little-mountain-4551"


def test_parse_returns_all_suburb_rows_including_richmond_hill():
    # Richmond fixture has 7 RICHMOND suburbs + 2 RICHMOND HILL + 1 RICHMOND LOWLANDS.
    matches = _parse_response(_load("richmond.json"))
    assert len(matches) == 10
    assert all(m.postcode and m.state and m.slug for m in matches)


def test_filter_matches_exact_name_match_richmond_returns_seven():
    matches = _parse_response(_load("richmond.json"))
    filtered = _filter_matches(matches, "Richmond", postcode=None, state=None)
    assert len(filtered) == 7
    assert {m.state for m in filtered} == {"NSW", "QLD", "SA", "TAS", "VIC"}


def test_filter_matches_with_state_disambiguates():
    matches = _parse_response(_load("richmond.json"))
    filtered = _filter_matches(matches, "Richmond", postcode=None, state="vic")
    assert len(filtered) == 1
    assert filtered[0].postcode == "3121"


def test_filter_matches_with_postcode_disambiguates():
    matches = _parse_response(_load("richmond.json"))
    filtered = _filter_matches(matches, "Richmond", postcode="2755", state=None)
    assert len(filtered) == 1
    assert filtered[0].state == "NSW"


def test_filter_matches_drops_richmond_hill():
    matches = _parse_response(_load("richmond.json"))
    filtered = _filter_matches(matches, "Richmond", postcode=None, state=None)
    names = {m.name for m in filtered}
    assert names == {"RICHMOND"}  # RICHMOND HILL / LOWLANDS excluded


def test_parse_malformed_payload_raises():
    with pytest.raises(ParseError):
        _parse_response({"unexpected": "shape"})
    with pytest.raises(ParseError):
        _parse_response({"content": "not-a-list"})
    with pytest.raises(ParseError):
        _parse_response("totally wrong")


def test_parse_row_missing_field_raises():
    bad = {"content": [{"streetNumber": "", "suburb": "X"}]}  # missing postCode/stateCode
    with pytest.raises(ParseError):
        _parse_response(bad)


def test_build_slug_lowercases_and_hyphenates():
    assert _build_slug("LITTLE MOUNTAIN", "4551") == "little-mountain-4551"
    assert _build_slug("South Hobart", "7004") == "south-hobart-7004"
