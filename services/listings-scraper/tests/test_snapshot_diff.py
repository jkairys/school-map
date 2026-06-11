"""Tests for the snapshot diff engine.

Table-driven coverage of every material field, the initial-observation
sentinel, whitespace normalisation, agent/agency-only no-change, property-type
case insensitivity, and a static import-purity check.
"""

import ast
from dataclasses import dataclass, replace

import pytest

from listings_scraper.snapshot_diff import (
    INITIAL_SENTINEL,
    MATERIAL_FIELDS,
    ChangedFields,
    diff,
)


@dataclass
class FakeListing:
    """Stand-in for VendorListing / ListingSnapshot.

    Carries the material fields plus agent/agency to prove the diff ignores
    them. Satisfies the `SnapshotLike` Protocol structurally.
    """

    price: int | None = 800_000
    price_display: str | None = "800000"
    price_kind: str | None = "price"
    title: str | None = "Lovely 3BR home"
    blurb: str | None = "Quiet street, north-facing."
    bedrooms: int | None = 3
    bathrooms: int | None = 2
    parking: int | None = 2
    land_size_sqm: int | None = 600
    property_type: str | None = "house"
    status: str | None = "ForSale"
    agent_name: str | None = "Pat Agent"
    agency_name: str | None = "Realty Co"


@pytest.fixture
def base() -> FakeListing:
    return FakeListing()


def test_material_fields_allow_list_is_exact():
    assert set(MATERIAL_FIELDS) == {
        "price",
        "price_display",
        "price_kind",
        "title",
        "blurb",
        "bedrooms",
        "bathrooms",
        "parking",
        "land_size_sqm",
        "property_type",
        "status",
    }


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("price", 750_000),
        ("price_display", "750000"),
        ("price_kind", "auction"),
        ("title", "Lovely 4BR home"),
        ("blurb", "Different blurb."),
        ("bedrooms", 4),
        ("bathrooms", 3),
        ("parking", 1),
        ("land_size_sqm", 650),
        ("property_type", "townhouse"),
        ("status", "Sold"),
    ],
)
def test_each_material_field_change_detected(base, field, new_value):
    new = replace(base, **{field: new_value})
    result = diff(base, new)
    assert result is not None
    assert list(result) == [field]


def test_identical_observation_returns_none(base):
    assert diff(base, replace(base)) is None


def test_whitespace_only_blurb_change_returns_none(base):
    new = replace(base, blurb="  Quiet  street,\n north-facing.  ")
    assert diff(base, new) is None


def test_whitespace_only_title_change_returns_none(base):
    new = replace(base, title="  Lovely   3BR home  ")
    assert diff(base, new) is None


def test_initial_observation_returns_initial_sentinel(base):
    result = diff(None, base)
    assert result is not None
    assert INITIAL_SENTINEL in result
    assert list(result)[0] == INITIAL_SENTINEL
    assert set(result) == {INITIAL_SENTINEL, *MATERIAL_FIELDS}


def test_initial_observation_skips_none_fields():
    sparse = FakeListing(blurb=None, land_size_sqm=None)
    result = diff(None, sparse)
    assert result is not None
    assert "blurb" not in result
    assert "land_size_sqm" not in result
    assert "price" in result


def test_agent_and_agency_change_alone_returns_none(base):
    new = replace(base, agent_name="Different Agent", agency_name="Different Agency")
    assert diff(base, new) is None


@pytest.mark.parametrize("variant", ["HOUSE", "House", "  house  ", "hOuSe"])
def test_property_type_case_and_whitespace_insensitive(base, variant):
    new = replace(base, property_type=variant)
    assert diff(base, new) is None


def test_property_type_real_change_detected(base):
    new = replace(base, property_type="Apartment")
    result = diff(base, new)
    assert result is not None
    assert list(result) == ["property_type"]


def test_null_equals_null():
    a = FakeListing(blurb=None)
    b = FakeListing(blurb=None)
    assert diff(a, b) is None


def test_null_to_value_is_change():
    a = FakeListing(blurb=None)
    b = FakeListing(blurb="now there's a blurb")
    result = diff(a, b)
    assert result is not None
    assert list(result) == ["blurb"]


def test_value_to_null_is_change():
    a = FakeListing(land_size_sqm=600)
    b = FakeListing(land_size_sqm=None)
    result = diff(a, b)
    assert result is not None
    assert list(result) == ["land_size_sqm"]


def test_multiple_changes_returned_in_canonical_order(base):
    new = replace(base, status="UnderContract", price=700_000, bedrooms=4)
    result = diff(base, new)
    assert result is not None
    assert list(result) == ["price", "bedrooms", "status"]


def test_changed_fields_is_iterable_and_sized():
    cf = ChangedFields(["price", "status"])
    assert len(cf) == 2
    assert list(cf) == ["price", "status"]
    assert "price" in cf
    assert "blurb" not in cf


def test_module_does_not_import_io_libraries():
    """Static AST check: snapshot_diff must not reference DB or HTTP libraries."""
    import listings_scraper.snapshot_diff as mod

    with open(mod.__file__) as f:
        tree = ast.parse(f.read())

    forbidden = {
        "sqlalchemy",
        "asyncpg",
        "psycopg",
        "psycopg2",
        "alembic",
        "httpx",
        "requests",
        "urllib3",
        "aiohttp",
        "camoufox",
        "playwright",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, (
                    f"snapshot_diff imports forbidden module: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, (
                f"snapshot_diff imports forbidden module: {node.module}"
            )
