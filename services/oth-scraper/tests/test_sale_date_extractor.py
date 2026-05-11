"""Unit tests for the SaleDateExtractor.

These tests are pure — no DB, no async, no I/O. They run from the fixture
corpus as well as synthetic edge-case payloads.

Key path confirmed: raw_payload['lastSale']['eventDate'] (ISO-8601 date
string). Absent from forsale/forrent fixtures; present and consistent across
all 24 recentlysold fixture entries.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from oth_scraper.sale_date_extractor import extract_sale_date

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "oth"


# ---- helpers ---------------------------------------------------------------


def _load_fixture(filename: str) -> list[dict]:
    """Load the 'content' list from an OTH fixture file."""
    with (_FIXTURE_DIR / filename).open() as fh:
        return json.load(fh)["content"]


# ---- field-present cases ---------------------------------------------------


def test_returns_date_for_standard_payload():
    """Minimal correct payload — returns the parsed date."""
    payload = {"lastSale": {"eventDate": "2026-04-28"}}
    assert extract_sale_date(payload) == date(2026, 4, 28)


def test_returns_date_for_all_recentlysold_fixture_entries():
    """Every entry in the fixture corpus must yield a valid date."""
    entries = _load_fixture("recentlysold_paddington_p0.json")
    assert len(entries) > 0, "fixture corpus must be non-empty"
    for i, entry in enumerate(entries):
        result = extract_sale_date(entry)
        assert result is not None, f"entry {i} returned None"
        assert isinstance(result, date), f"entry {i} is not a date: {result!r}"


def test_fixture_dates_are_in_expected_range():
    """Fixture sale dates should be plausible (not in far future/past)."""
    entries = _load_fixture("recentlysold_paddington_p0.json")
    for entry in entries:
        d = extract_sale_date(entry)
        assert d is not None
        assert date(2020, 1, 1) <= d <= date(2030, 1, 1), f"suspicious date: {d}"


# ---- field-missing cases ---------------------------------------------------


def test_returns_none_for_empty_payload():
    """Empty dict — no key path present."""
    assert extract_sale_date({}) is None


def test_returns_none_when_last_sale_absent():
    """Payload without 'lastSale' key."""
    assert extract_sale_date({"address": {"suburb": "Paddington"}}) is None


def test_returns_none_when_event_date_absent():
    """'lastSale' present but 'eventDate' missing."""
    payload = {"lastSale": {"salePrice": 1_500_000, "type": "SoldEvent"}}
    assert extract_sale_date(payload) is None


def test_returns_none_when_last_sale_not_a_dict():
    """'lastSale' present but not a dict (defensive guard)."""
    assert extract_sale_date({"lastSale": "2026-04-28"}) is None
    assert extract_sale_date({"lastSale": None}) is None
    assert extract_sale_date({"lastSale": 42}) is None


def test_returns_none_when_event_date_is_none():
    """'eventDate' key exists but value is None."""
    payload = {"lastSale": {"eventDate": None}}
    assert extract_sale_date(payload) is None


# ---- malformed date cases --------------------------------------------------


def test_returns_none_for_non_iso_date_string():
    """Malformed date strings must not raise — return None instead."""
    assert extract_sale_date({"lastSale": {"eventDate": "not-a-date"}}) is None
    assert extract_sale_date({"lastSale": {"eventDate": "28/04/2026"}}) is None
    assert extract_sale_date({"lastSale": {"eventDate": "April 28, 2026"}}) is None
    assert extract_sale_date({"lastSale": {"eventDate": ""}}) is None


def test_returns_none_for_datetime_string():
    """ISO datetime string (with time component) is not a valid date — return None."""
    # date.fromisoformat in Python 3.11+ accepts "2026-04-28T00:00:00", so we
    # allow that case to succeed (it still yields a valid date implicitly via
    # datetime parsing).  Strings with timezone offsets are non-parseable.
    assert extract_sale_date({"lastSale": {"eventDate": "2026-04-28T10:00:00+10:00"}}) is None


def test_returns_none_for_numeric_event_date():
    """Numeric value for eventDate must not raise."""
    assert extract_sale_date({"lastSale": {"eventDate": 20260428}}) is None


# ---- non-recentlysold fixture payloads (extractor should return None) ------


def test_returns_none_for_forsale_fixture_entries():
    """forsale payloads have no 'lastSale' key — extractor returns None."""
    entries = _load_fixture("forsale_paddington_p0.json")
    assert len(entries) > 0
    for i, entry in enumerate(entries):
        result = extract_sale_date(entry)
        assert result is None, f"forsale entry {i} unexpectedly returned {result!r}"


def test_returns_none_for_forrent_fixture_entries():
    """forrent payloads have no 'lastSale' key — extractor returns None."""
    entries = _load_fixture("forrent_paddington_p0.json")
    assert len(entries) > 0
    for i, entry in enumerate(entries):
        result = extract_sale_date(entry)
        assert result is None, f"forrent entry {i} unexpectedly returned {result!r}"
