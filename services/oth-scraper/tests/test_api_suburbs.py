"""REST endpoint tests for /suburbs/resolve."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from oth_scraper.api.app import app
from oth_scraper.db.engine import Base, get_db
from oth_scraper.db.models.suburb import Suburb  # noqa: F401  (register on metadata)

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest_asyncio.fixture
async def api_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
    assert body["oth_slug"] == "little-mountain-4551"


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
