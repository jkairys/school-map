"""REST endpoint tests for /scrape-lists.

Uses the postgres testcontainer (filters is JSONB; scrape_list_suburb has FK
constraints) — same pattern as test_queue.py.
"""
import json
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.api.app import app
from listings_scraper.db.engine import get_db

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------- create / get / list / update / delete ----------


async def test_create_scrape_list_minimal(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={"name": "Sunshine Coast family homes"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "Sunshine Coast family homes"
    assert body["description"] is None
    assert body["filters"] == {
        "beds_min": None,
        "beds_max": None,
        "property_types": None,
        "price_min": None,
        "price_max": None,
    }
    assert body["cron_schedule"] is None
    assert body["suburbs"] == []


async def test_create_scrape_list_with_filters(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={
            "name": "rental search",
            "description": "looking for a rental",
            "filters": {
                "beds_min": 3,
                "beds_max": 4,
                "property_types": ["House", "Townhouse"],
                "price_max": 1500000,
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filters"]["beds_min"] == 3
    assert body["filters"]["beds_max"] == 4
    assert body["filters"]["property_types"] == ["House", "Townhouse"]
    assert body["filters"]["price_max"] == 1500000


async def test_create_scrape_list_with_cron_schedule_accepted(api_client):
    """v1 ignores cron_schedule but the column accepts a string and null."""
    r = await api_client.post(
        "/scrape-lists",
        json={"name": "cron later", "cron_schedule": "0 6 * * *"},
    )
    assert r.status_code == 201
    assert r.json()["cron_schedule"] == "0 6 * * *"


async def test_get_scrape_list(api_client):
    created = (
        await api_client.post("/scrape-lists", json={"name": "alpha"})
    ).json()
    r = await api_client.get(f"/scrape-lists/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]
    assert r.json()["suburbs"] == []


async def test_get_scrape_list_404(api_client):
    r = await api_client.get("/scrape-lists/999999")
    assert r.status_code == 404


async def test_list_scrape_lists(api_client):
    await api_client.post("/scrape-lists", json={"name": "alpha"})
    await api_client.post("/scrape-lists", json={"name": "beta"})

    r = await api_client.get("/scrape-lists")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    names = {row["name"] for row in body}
    assert names == {"alpha", "beta"}
    assert all(row["suburb_count"] == 0 for row in body)


async def test_update_scrape_list(api_client):
    created = (
        await api_client.post("/scrape-lists", json={"name": "old"})
    ).json()
    r = await api_client.put(
        f"/scrape-lists/{created['id']}",
        json={
            "name": "new",
            "description": "updated",
            "filters": {"beds_min": 2},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "new"
    assert body["description"] == "updated"
    assert body["filters"]["beds_min"] == 2


async def test_update_scrape_list_404(api_client):
    r = await api_client.put(
        "/scrape-lists/999999", json={"name": "missing"}
    )
    assert r.status_code == 404


async def test_delete_scrape_list_cascades_m2m_only(
    api_client, session_factory, httpx_mock
):
    """Deleting a list removes its m2m rows but leaves suburb rows intact."""
    from sqlalchemy import select

    from listings_scraper.db.models.scrape_list import ScrapeList, ScrapeListSuburb
    from listings_scraper.db.models.suburb import Suburb

    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "to delete"})
    ).json()["id"]
    add = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs",
        json={"name": "Little Mountain"},
    )
    assert add.status_code == 200, add.text
    suburb_id = add.json()["id"]

    r = await api_client.delete(f"/scrape-lists/{list_id}")
    assert r.status_code == 204

    async with session_factory() as s:
        assert (await s.get(ScrapeList, list_id)) is None
        assert (await s.get(Suburb, suburb_id)) is not None
        m2m = (
            await s.execute(
                select(ScrapeListSuburb).where(
                    ScrapeListSuburb.scrape_list_id == list_id
                )
            )
        ).all()
        assert m2m == []


# ---------- filter validation ----------


async def test_create_rejects_unknown_filter_keys_with_422(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={"name": "bad", "filters": {"bathrooms_min": 2}},
    )
    assert r.status_code == 422
    detail = json.dumps(r.json())
    assert "extra" in detail.lower() or "forbid" in detail.lower() or "bathrooms_min" in detail


async def test_create_rejects_negative_numbers_with_422(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={"name": "bad", "filters": {"price_min": -1}},
    )
    assert r.status_code == 422


async def test_create_rejects_inverted_beds_range_with_422(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={"name": "bad", "filters": {"beds_min": 5, "beds_max": 3}},
    )
    assert r.status_code == 422


async def test_create_rejects_inverted_price_range_with_422(api_client):
    r = await api_client.post(
        "/scrape-lists",
        json={
            "name": "bad",
            "filters": {"price_min": 2_000_000, "price_max": 1_000_000},
        },
    )
    assert r.status_code == 422


async def test_update_rejects_invalid_filters_with_422(api_client):
    created = (
        await api_client.post("/scrape-lists", json={"name": "x"})
    ).json()
    r = await api_client.put(
        f"/scrape-lists/{created['id']}",
        json={"filters": {"unknown": True}},
    )
    assert r.status_code == 422


# ---------- suburb add / remove ----------


async def test_add_suburb_resolves_and_attaches(api_client, httpx_mock):
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "qld"})
    ).json()["id"]

    r = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs", json={"name": "Little Mountain"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["postcode"] == "4551"
    assert body["state"] == "QLD"

    show = await api_client.get(f"/scrape-lists/{list_id}")
    assert len(show.json()["suburbs"]) == 1
    assert show.json()["suburbs"][0]["postcode"] == "4551"


async def test_add_ambiguous_suburb_returns_409_with_candidates(
    api_client, httpx_mock
):
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Richmond",
        json=_fixture("richmond.json"),
    )
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "richmond test"})
    ).json()["id"]

    r = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs", json={"name": "Richmond"}
    )
    assert r.status_code == 409
    candidates = r.json()["detail"]["candidates"]
    assert len(candidates) == 7
    assert {c["state"] for c in candidates} == {"NSW", "QLD", "SA", "TAS", "VIC"}


async def test_add_ambiguous_suburb_resolves_with_state(
    api_client, httpx_mock
):
    """The 409 contract: caller retries with (name, postcode/state)."""
    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Richmond",
        json=_fixture("richmond.json"),
    )
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "richmond"})
    ).json()["id"]

    r = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs",
        json={"name": "Richmond", "state": "VIC"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "VIC"
    assert r.json()["postcode"] == "3121"


async def test_remove_suburb_does_not_delete_suburb_row(
    api_client, session_factory, httpx_mock
):
    from listings_scraper.db.models.suburb import Suburb

    httpx_mock.add_response(
        url="https://www.onthehouse.com.au/odin/api/locations?query=Little+Mountain",
        json=_fixture("little_mountain.json"),
    )
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "remove test"})
    ).json()["id"]
    add = await api_client.post(
        f"/scrape-lists/{list_id}/suburbs", json={"name": "Little Mountain"}
    )
    suburb_id = add.json()["id"]

    r = await api_client.delete(
        f"/scrape-lists/{list_id}/suburbs/{suburb_id}"
    )
    assert r.status_code == 204

    show = await api_client.get(f"/scrape-lists/{list_id}")
    assert show.json()["suburbs"] == []

    async with session_factory() as s:
        suburb_row = await s.get(Suburb, suburb_id)
        assert suburb_row is not None
        assert suburb_row.name == "LITTLE MOUNTAIN"


async def test_remove_suburb_404_if_not_in_list(api_client):
    list_id = (
        await api_client.post("/scrape-lists", json={"name": "x"})
    ).json()["id"]
    r = await api_client.delete(f"/scrape-lists/{list_id}/suburbs/9999999")
    assert r.status_code == 404


async def test_add_suburb_to_missing_list_404(api_client):
    r = await api_client.post(
        "/scrape-lists/999999/suburbs", json={"name": "Little Mountain"}
    )
    assert r.status_code == 404
