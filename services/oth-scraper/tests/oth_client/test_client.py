"""End-to-end tests for `OTHApiClient` using a mocked httpx client.

These tests exercise the full path the worker loop will take: build payload
→ POST → parse response. We use `pytest-httpx` to mock the network so the
test runs offline.
"""

import json
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from oth_scraper.oth_client import (
    Category,
    ListingFilters,
    OTHApiClient,
    PriceUnit,
    PropertyType,
    ResolvedSuburb,
)
from oth_scraper.oth_client.payload import SEARCH_URL


PADDINGTON = ResolvedSuburb(name="Paddington", state="QLD", postcode="4064")


def _load(oth_fixtures_dir: Path, name: str) -> dict:
    return json.loads((oth_fixtures_dir / name).read_text())


async def test_search_posts_built_payload_to_oth(
    httpx_mock: HTTPXMock, oth_fixtures_dir: Path
) -> None:
    """The client should POST to OTH's search URL with the payload from
    `build_search_payload` and return the parsed `SearchPage`."""
    httpx_mock.add_response(
        method="POST",
        url=SEARCH_URL,
        json=_load(oth_fixtures_dir, "forrent_paddington_p0.json"),
    )

    client = OTHApiClient()
    filters = ListingFilters(beds_min=2, property_types=(PropertyType.APARTMENT,))
    async with httpx.AsyncClient() as http:
        page = await client.search(
            PADDINGTON, Category.FORRENT, filters, page=0, http=http
        )

    sent = httpx_mock.get_request()
    assert sent is not None
    body = json.loads(sent.content)
    target = body["query"]["queries"][0]
    assert target["category"] == "RentalListing"
    assert target["status"] == "current"
    # Filter keys are inlined into the per-suburb target object as
    # string-encoded scalars; OTH 400s on nested ranges or top-level keys.
    assert target["bedsMin"] == "2"
    assert target["types"] == ["Apartment"]

    assert page.total == 11
    assert len(page.listings) == 11
    assert page.listings[0].price_unit is PriceUnit.WEEKLY


async def test_search_propagates_extra_headers(httpx_mock: HTTPXMock) -> None:
    """The session bootstrap (issue 10) hands us anti-bot cookies + headers
    via the httpx client and via `extra_headers`; both must reach OTH."""
    httpx_mock.add_response(
        method="POST",
        url=SEARCH_URL,
        json={"content": [], "totalElements": 0, "number": 0, "last": True},
    )

    client = OTHApiClient()
    async with httpx.AsyncClient() as http:
        await client.search(
            PADDINGTON,
            Category.FORSALE,
            ListingFilters(),
            page=0,
            http=http,
            extra_headers={"x-test-token": "abc"},
        )

    sent = httpx_mock.get_request()
    assert sent is not None
    assert sent.headers.get("x-test-token") == "abc"
    assert sent.headers.get("content-type") == "application/json"


async def test_search_raises_on_non_2xx(httpx_mock: HTTPXMock) -> None:
    """5xx surfaces as `HTTPStatusError` so the worker loop can classify
    it as transient."""
    httpx_mock.add_response(method="POST", url=SEARCH_URL, status_code=503, text="upstream down")

    client = OTHApiClient()
    async with httpx.AsyncClient() as http:
        with pytest.raises(httpx.HTTPStatusError):
            await client.search(
                PADDINGTON, Category.FORSALE, ListingFilters(), page=0, http=http
            )


async def test_search_pagination_request_carries_page_number(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=SEARCH_URL,
        json={"content": [], "totalElements": 0, "number": 3, "last": True},
    )
    client = OTHApiClient()
    async with httpx.AsyncClient() as http:
        page = await client.search(
            PADDINGTON, Category.FORSALE, ListingFilters(), page=3, http=http
        )

    sent = httpx_mock.get_request()
    assert sent is not None
    body = json.loads(sent.content)
    assert body["number"] == 3
    assert page.page == 3
