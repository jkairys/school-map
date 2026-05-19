"""End-to-end tests for `OTHApiClient` using a mocked httpx transport.

These tests exercise the full path the worker loop will take: build payload
→ POST → parse response. We use `httpx.MockTransport` (injected via a fake
ScrapeSession) to mock the network so the tests run offline.
"""

import json
from pathlib import Path

import httpx
import pytest

from listings_scraper.oth_client import (
    Category,
    ListingFilters,
    OTHApiClient,
    PropertyType,
    ResolvedSuburb,
)
from listings_scraper.oth_client.payload import SEARCH_URL
from listings_scraper.vendor_clients.base import PriceKind


from datetime import datetime, timezone

PADDINGTON = ResolvedSuburb(
    id=1, name="Paddington", state="QLD", postcode="4064",
    resolved_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
)


def _load(oth_fixtures_dir: Path, name: str) -> dict:
    return json.loads((oth_fixtures_dir / name).read_text())


def _make_fake_session(response_body: dict | None = None, *, status_code: int = 200):
    """Build a minimal fake ScrapeSession backed by an httpx.MockTransport.

    The fake exposes only `async def http() -> httpx.AsyncClient` — the sole
    method OTHApiClient needs from a ScrapeSession.
    """
    if response_body is not None:
        body_bytes = json.dumps(response_body).encode()
    else:
        body_bytes = b""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            headers={"content-type": "application/json"},
            content=body_bytes,
            request=request,
        )

    transport = httpx.MockTransport(handler)

    class _FakeSession:
        _client: httpx.AsyncClient | None = None

        async def http(self) -> httpx.AsyncClient:
            if self._client is None:
                self._client = httpx.AsyncClient(transport=transport)
            return self._client

    return _FakeSession()


async def test_search_posts_built_payload_to_oth(oth_fixtures_dir: Path) -> None:
    """The client should POST to OTH's search URL with the payload from
    `build_search_payload` and return the parsed `SearchPage`."""
    body = _load(oth_fixtures_dir, "forrent_paddington_p0.json")

    sent_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(body).encode(),
            request=request,
        )

    class _FakeSession:
        async def http(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client = OTHApiClient()
    filters = ListingFilters(beds_min=2, property_types=(PropertyType.APARTMENT,))
    page = await client.search(
        PADDINGTON, Category.FORRENT, filters, page=0, session=_FakeSession()
    )

    assert len(sent_requests) == 1
    sent = sent_requests[0]
    assert str(sent.url) == SEARCH_URL
    payload = json.loads(sent.content)
    target = payload["query"]["queries"][0]
    assert target["category"] == "RentalListing"
    assert target["status"] == "current"
    assert target["bedsMin"] == "2"
    assert target["types"] == ["Apartment"]

    assert page.total == 11
    assert len(page.listings) == 11
    assert page.listings[0].price_kind is PriceKind.RENT_WEEKLY


async def test_search_sends_json_content_type() -> None:
    """The client must always send content-type: application/json."""
    sent_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(
                {"content": [], "totalElements": 0, "number": 0, "last": True}
            ).encode(),
            request=request,
        )

    class _FakeSession:
        async def http(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client = OTHApiClient()
    await client.search(
        PADDINGTON,
        Category.FORSALE,
        ListingFilters(),
        page=0,
        session=_FakeSession(),
    )

    assert len(sent_requests) == 1
    assert sent_requests[0].headers.get("content-type") == "application/json"


async def test_search_raises_on_non_2xx() -> None:
    """5xx surfaces as `HTTPStatusError` so the worker loop can classify
    it as transient."""
    session = _make_fake_session(status_code=503)

    client = OTHApiClient()
    with pytest.raises(httpx.HTTPStatusError):
        await client.search(
            PADDINGTON, Category.FORSALE, ListingFilters(), page=0, session=session
        )


async def test_search_pagination_request_carries_page_number() -> None:
    body = {"content": [], "totalElements": 0, "number": 3, "last": True}
    sent_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(body).encode(),
            request=request,
        )

    class _FakeSession:
        async def http(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    client = OTHApiClient()
    page = await client.search(
        PADDINGTON, Category.FORSALE, ListingFilters(), page=3, session=_FakeSession()
    )

    assert len(sent_requests) == 1
    payload = json.loads(sent_requests[0].content)
    assert payload["number"] == 3
    assert page.page == 3
