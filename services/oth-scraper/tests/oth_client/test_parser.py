"""Parser tests, table-driven against the recorded OTH fixtures.

The fixtures under `tests/fixtures/oth/` are captured by
`scripts/capture_fixtures.py` against the live OTH search API and committed
to the repo. They are the source of truth for response shape; if OTH ships
a schema change, re-capture and update assertions here.

Tests are split into:
- per-fixture parse smoke (every record decodes into a typed `OTHListing`),
- per-category invariants (status, price_unit, agent locations, etc),
- edge-case tests using small inline payloads that target specific branches
  of the parser (missing land size, missing lat/lon, multiple agents,
  weekly-rent integer, free-text displayPrice with/without dollar amount).
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from oth_scraper.oth_client import Category, PriceUnit
from oth_scraper.oth_client.exceptions import ParseError
from oth_scraper.oth_client.parser import parse_search_response


def _load_fixture(oth_fixtures_dir: Path, name: str) -> dict:
    return json.loads((oth_fixtures_dir / name).read_text())


FIXTURES = [
    pytest.param(
        "forsale_paddington_p0.json", Category.FORSALE, "current", PriceUnit.TOTAL,
        id="forsale-paddington",
    ),
    pytest.param(
        "forrent_paddington_p0.json", Category.FORRENT, "current", PriceUnit.WEEKLY,
        id="forrent-paddington",
    ),
    pytest.param(
        "recentlysold_paddington_p0.json", Category.RECENTLYSOLD, "sold", PriceUnit.TOTAL,
        id="recentlysold-paddington",
    ),
]


@pytest.mark.parametrize("filename,category,expected_default_status,expected_price_unit", FIXTURES)
def test_parse_fixture_smoke(
    oth_fixtures_dir: Path,
    filename: str,
    category: Category,
    expected_default_status: str,
    expected_price_unit: PriceUnit,
) -> None:
    body = _load_fixture(oth_fixtures_dir, filename)
    result = parse_search_response(body, category=category, page=0)

    assert result.page == 0
    assert result.total >= len(result.listings)
    assert len(result.listings) == len(body["content"])

    for listing in result.listings:
        assert listing.oth_property_id, "every record must have an oth_property_id"
        assert listing.formatted_address, "every record must have an address"
        assert listing.postcode, "every record must have a postcode"
        assert listing.title == listing.formatted_address
        assert listing.price_unit is expected_price_unit

    # `status` is always one of the known values for the category.
    statuses = {l.status for l in result.listings}
    if category is Category.FORSALE:
        assert statuses <= {"current", "under_offer"}
    else:
        assert statuses == {expected_default_status}


def test_parse_forsale_first_record(oth_fixtures_dir: Path) -> None:
    body = _load_fixture(oth_fixtures_dir, "forsale_paddington_p0.json")
    page = parse_search_response(body, category=Category.FORSALE, page=0)
    first = page.listings[0]

    assert first.oth_property_id == "3183143"
    assert first.formatted_address == "115 ROCKBOURNE TCE, PADDINGTON, QLD 4064"
    assert first.postcode == "4064"
    assert first.bedrooms == 5
    assert first.bathrooms == 3
    assert first.parking == 1
    assert first.property_type == "House"
    assert first.agent_name == "Jack Dixon"
    assert first.agency_name == "Dixon Family Estate Agents"
    assert first.status == "current"
    assert first.price_unit is PriceUnit.TOTAL
    assert first.listing_url and first.listing_url.startswith(
        "https://www.onthehouse.com.au/property-for-sale/"
    )


def test_parse_forrent_first_record_has_weekly_rent_int(oth_fixtures_dir: Path) -> None:
    body = _load_fixture(oth_fixtures_dir, "forrent_paddington_p0.json")
    page = parse_search_response(body, category=Category.FORRENT, page=0)
    first = page.listings[0]

    # Weekly-rent string parsed to int — issue 05 acceptance criterion.
    assert isinstance(first.price, int)
    assert first.price == 950
    assert first.price_unit is PriceUnit.WEEKLY
    assert first.status == "current"
    assert first.listing_url and "/property-for-rent/" in first.listing_url


def test_parse_recentlysold_first_record(oth_fixtures_dir: Path) -> None:
    body = _load_fixture(oth_fixtures_dir, "recentlysold_paddington_p0.json")
    page = parse_search_response(body, category=Category.RECENTLYSOLD, page=0)
    first = page.listings[0]

    assert first.oth_property_id == "3177937"
    assert first.price == 1_950_000
    assert first.price_unit is PriceUnit.TOTAL
    assert first.status == "sold"
    # RecentlySold records pull agency from `lastSale.sellingAgency`, not
    # from the absent `listing.agency` block.
    assert first.agency_name == "Place Property Paddington"


def test_parse_forsale_includes_listing_with_dollar_displayprice(
    oth_fixtures_dir: Path,
) -> None:
    """At least one ForSale fixture record exposes a parseable $ amount."""
    body = _load_fixture(oth_fixtures_dir, "forsale_paddington_p0.json")
    page = parse_search_response(body, category=Category.FORSALE, page=0)
    priced = [l for l in page.listings if l.price is not None]
    assert priced, "expected at least one ForSale listing with a parseable price"
    for l in priced:
        assert l.price >= 100_000
        assert l.price_unit is PriceUnit.TOTAL


def test_parse_forsale_multi_agent_takes_first(oth_fixtures_dir: Path) -> None:
    """When OTH lists multiple agents on a SaleListing, parser keeps only
    the first — issue 05 acceptance criterion."""
    body = _load_fixture(oth_fixtures_dir, "forsale_paddington_p0.json")
    multi_agent_records = [
        item
        for item in body["content"]
        if len(((item.get("listing") or {}).get("agency") or {}).get("agents", []) or []) > 1
    ]
    assert multi_agent_records, "fixture is missing multi-agent records"
    page = parse_search_response(body, category=Category.FORSALE, page=0)
    by_id = {l.oth_property_id: l for l in page.listings}

    for raw in multi_agent_records:
        parsed = by_id[str(raw["othPropertyId"])]
        first_agent_name = raw["listing"]["agency"]["agents"][0]["name"]
        assert parsed.agent_name == first_agent_name


def test_parse_forrent_records_missing_land_size_yield_none(oth_fixtures_dir: Path) -> None:
    body = _load_fixture(oth_fixtures_dir, "forrent_paddington_p0.json")
    page = parse_search_response(body, category=Category.FORRENT, page=0)
    no_land = [l for l in page.listings if l.land_size_sqm is None]
    assert no_land, "expected at least one rental listing without land size"


def test_parse_forrent_records_missing_lat_lon_yield_none(oth_fixtures_dir: Path) -> None:
    body = _load_fixture(oth_fixtures_dir, "forrent_paddington_p0.json")
    page = parse_search_response(body, category=Category.FORRENT, page=0)
    no_loc = [l for l in page.listings if l.latitude is None and l.longitude is None]
    assert no_loc, "expected at least one rental listing without lat/lon"


def test_parse_pagination_metadata(oth_fixtures_dir: Path) -> None:
    sale = parse_search_response(
        _load_fixture(oth_fixtures_dir, "forsale_paddington_p0.json"),
        category=Category.FORSALE, page=0,
    )
    rent = parse_search_response(
        _load_fixture(oth_fixtures_dir, "forrent_paddington_p0.json"),
        category=Category.FORRENT, page=0,
    )

    # forsale Paddington has 34 totalElements over 2 pages; page 0 is not last.
    assert sale.total == 34
    assert sale.has_next is True
    # forrent Paddington has 11 totalElements on a single page; page 0 is last.
    assert rent.total == 11
    assert rent.has_next is False


# ---------------------------------------------------------------------------
# Edge-case tests on small inline payloads — targeted at single parser branches.
# ---------------------------------------------------------------------------


def _minimal_sale_record(**overrides) -> dict:
    """Build a minimal SaleListing record we can mutate per test."""
    rec = {
        "category": "SaleListing",
        "othPropertyId": "111",
        "address": {
            "formattedAddress": "1 TEST ST, TESTVILLE, QLD 4000",
            "postCode": "4000",
            "location": {"lat": -27.0, "lon": 153.0},
        },
        "beds": 3,
        "baths": 2,
        "carSpaces": 1,
        "landSize": 500,
        "landSizeUnit": "squareMeter",
        "type": "House",
        "listing": {
            "displayPrice": "For Sale",
            "agency": {"name": "Test Agency", "agents": [{"name": "Alice"}]},
        },
        "underOffer": False,
        "links": [
            {"rel": "othWebUrl", "href": "https://example.test/listing/111"},
        ],
    }
    rec.update(overrides)
    return rec


def _wrap(records: list[dict]) -> dict:
    return {
        "content": records,
        "totalElements": len(records),
        "totalPages": 1,
        "number": 0,
        "last": True,
    }


def test_displayprice_with_dollar_amount_is_parsed_to_int() -> None:
    rec = _minimal_sale_record()
    rec["listing"]["displayPrice"] = "Offers Over $1,485,000"
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].price == 1_485_000


def test_displayprice_without_dollar_amount_is_none() -> None:
    rec = _minimal_sale_record()
    rec["listing"]["displayPrice"] = "By Negotiation"
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].price is None


def test_displayprice_below_floor_is_dropped() -> None:
    """`Early $2m` shouldn't parse to $2 — the regex would catch the digit
    but the floor guard discards it."""
    rec = _minimal_sale_record()
    rec["listing"]["displayPrice"] = "Inviting Offers in the Early $2m"
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].price is None


def test_under_offer_flag_promotes_status() -> None:
    rec = _minimal_sale_record(underOffer=True)
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].status == "under_offer"


def test_missing_land_size_yields_none() -> None:
    rec = _minimal_sale_record()
    rec["landSize"] = None
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].land_size_sqm is None


def test_missing_lat_lon_yields_none() -> None:
    rec = _minimal_sale_record()
    rec["address"]["location"] = None
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    listing = page.listings[0]
    assert listing.latitude is None
    assert listing.longitude is None


def test_unknown_land_size_unit_drops_value() -> None:
    rec = _minimal_sale_record()
    rec["landSize"] = 2
    rec["landSizeUnit"] = "acre"  # not squareMeter — would be wrong to coerce
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].land_size_sqm is None


def test_multiple_agents_keeps_only_first() -> None:
    rec = _minimal_sale_record()
    rec["listing"]["agency"]["agents"] = [
        {"name": "Alice"},
        {"name": "Bob"},
        {"name": "Charlie"},
    ]
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].agent_name == "Alice"


def test_zero_agents_yields_none_agent_name() -> None:
    rec = _minimal_sale_record()
    rec["listing"]["agency"]["agents"] = []
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].agent_name is None
    assert page.listings[0].agency_name == "Test Agency"


def test_forrent_weekly_rent_uses_listing_price() -> None:
    rec = _minimal_sale_record()
    rec["category"] = "RentalListing"
    rec["listing"]["price"] = 725
    rec["listing"]["displayPrice"] = "$725 per week"
    page = parse_search_response(_wrap([rec]), category=Category.FORRENT, page=0)
    listing = page.listings[0]
    assert listing.price == 725
    assert listing.price_unit is PriceUnit.WEEKLY


def test_forrent_missing_price_yields_none() -> None:
    rec = _minimal_sale_record()
    rec["category"] = "RentalListing"
    rec["listing"]["price"] = None
    rec["listing"]["displayPrice"] = "CONTACT AGENT"
    page = parse_search_response(_wrap([rec]), category=Category.FORRENT, page=0)
    listing = page.listings[0]
    assert listing.price is None
    assert listing.price_unit is PriceUnit.WEEKLY


def test_recentlysold_pulls_price_and_agency_from_last_sale() -> None:
    rec = _minimal_sale_record()
    rec["category"] = "Property"
    rec["listing"] = {}
    rec["lastSale"] = {
        "salePrice": 1_750_000,
        "eventDate": "2026-04-01",
        "sellingAgency": {"name": "Sold By Co", "agents": [{"name": "Selling Sam"}]},
    }
    page = parse_search_response(_wrap([rec]), category=Category.RECENTLYSOLD, page=0)
    listing = page.listings[0]
    assert listing.price == 1_750_000
    assert listing.price_unit is PriceUnit.TOTAL
    assert listing.status == "sold"
    assert listing.agency_name == "Sold By Co"
    assert listing.agent_name == "Selling Sam"


def test_listing_url_extracted_from_oth_web_url_link() -> None:
    rec = _minimal_sale_record()
    rec["links"] = [
        {"rel": "self", "href": "https://api/listings/111"},
        {"rel": "agency", "href": "https://api/agency/1"},
        {"rel": "othWebUrl", "href": "https://www.onthehouse.com.au/whatever/111"},
    ]
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].listing_url == "https://www.onthehouse.com.au/whatever/111"


def test_listing_url_none_when_no_oth_web_url_link() -> None:
    rec = _minimal_sale_record()
    rec["links"] = [{"rel": "self", "href": "https://api/listings/111"}]
    page = parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)
    assert page.listings[0].listing_url is None


def test_parse_error_when_oth_property_id_missing() -> None:
    rec = _minimal_sale_record()
    del rec["othPropertyId"]
    with pytest.raises(ParseError, match="othPropertyId"):
        parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)


def test_parse_error_when_address_missing() -> None:
    rec = _minimal_sale_record()
    rec["address"] = {}
    with pytest.raises(ParseError, match="formattedAddress"):
        parse_search_response(_wrap([rec]), category=Category.FORSALE, page=0)


def test_parse_error_when_content_missing() -> None:
    with pytest.raises(ParseError, match="content"):
        parse_search_response({"totalElements": 0}, category=Category.FORSALE, page=0)


def test_parse_error_when_body_not_object() -> None:
    with pytest.raises(ParseError):
        parse_search_response([], category=Category.FORSALE, page=0)  # type: ignore[arg-type]


def test_empty_content_yields_empty_page() -> None:
    page = parse_search_response(_wrap([]), category=Category.FORSALE, page=0)
    assert page.listings == []
    assert page.total == 0
    assert page.has_next is False


def test_has_next_true_when_last_flag_false() -> None:
    body = _wrap([])
    body["last"] = False
    body["totalElements"] = 100
    page = parse_search_response(body, category=Category.FORSALE, page=0)
    assert page.has_next is True
    assert page.total == 100


def test_fixture_data_is_not_mutated_by_parser(oth_fixtures_dir: Path) -> None:
    """Sanity: parsing must not mutate its input dict (raw_payload reuse)."""
    body = _load_fixture(oth_fixtures_dir, "forsale_paddington_p0.json")
    snapshot = deepcopy(body)
    parse_search_response(body, category=Category.FORSALE, page=0)
    assert body == snapshot
