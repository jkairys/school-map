"""REST endpoint tests for /suburbs/resolve and /suburbs/{id}."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from listings_scraper.api.app import app
from listings_scraper.db.engine import get_db
from listings_scraper.db.models.suburb import Suburb

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest_asyncio.fixture
async def api_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # See test_suburb_resolver: only the suburb table is sqlite-safe.
        await conn.run_sync(lambda c: Suburb.__table__.create(c))
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with sm() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_resolve_endpoint_200_single_match(api_client, httpx_mock):
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    r = await api_client.post("/suburbs/resolve", json={"name": "Little Mountain"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "LITTLE MOUNTAIN"
    assert body["postcode"] == "4551"
    assert body["state"] == "QLD"
    assert body["slug"] == "little-mountain-4551"


async def test_resolve_endpoint_409_with_candidates(api_client, httpx_mock):
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Richmond",
        json=_fixture("richmond.json"),
    )
    r = await api_client.post("/suburbs/resolve", json={"name": "Richmond"})
    assert r.status_code == 409
    candidates = r.json()["detail"]["candidates"]
    assert len(candidates) == 7
    assert {c["state"] for c in candidates} == {"NSW", "QLD", "SA", "TAS", "VIC"}


async def test_resolve_endpoint_idempotent_cached(api_client, httpx_mock):
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    first = await api_client.post("/suburbs/resolve", json={"name": "Little Mountain"})
    second = await api_client.post("/suburbs/resolve", json={"name": "Little Mountain"})

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    # Only one HTTP call should have been made to OTH.
    assert len(httpx_mock.get_requests()) == 1


async def test_get_suburb_200(api_client, httpx_mock):
    """GET /suburbs/{id} returns the suburb DTO after it has been resolved."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    resolved = await api_client.post("/suburbs/resolve", json={"name": "Little Mountain"})
    assert resolved.status_code == 200
    suburb_id = resolved.json()["id"]

    r = await api_client.get(f"/suburbs/{suburb_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == suburb_id
    assert body["name"] == "LITTLE MOUNTAIN"
    assert body["postcode"] == "4551"
    assert body["state"] == "QLD"
    assert body["slug"] == "little-mountain-4551"
    assert "resolved_at" in body


async def test_get_suburb_404(api_client):
    """GET /suburbs/{id} returns 404 for an unknown id."""
    r = await api_client.get("/suburbs/99999")
    assert r.status_code == 404
