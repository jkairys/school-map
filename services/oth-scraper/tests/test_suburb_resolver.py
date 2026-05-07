"""End-to-end resolver tests with mocked OTH and an in-memory sqlite DB."""

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oth_scraper.db.models.suburb import Suburb
from oth_scraper.suburb_resolver import (
    AutocompleteUnavailableError,
    Match,
    NoMatchError,
    ResolvedSuburb,
    resolve,
)

FIXTURES = Path(__file__).parent / "fixtures" / "oth" / "locations"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    # In-memory sqlite is fine: we only exercise CRUD against the suburb table
    # in these tests; coordination/integration tests use real Postgres.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Only create the suburb table — other models (e.g. scrape_job) use
        # Postgres-only types like JSONB and would fail under sqlite.
        await conn.run_sync(lambda c: Suburb.__table__.create(c))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


def _mock_client_returning(payload: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/odin/api/locations"
        assert "query" in request.url.params
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_resolve_single_match_returns_resolved_and_persists(session):
    async with _mock_client_returning(_fixture("little_mountain.json")) as client:
        result = await resolve("Little Mountain", session=session, client=client)

    assert isinstance(result, ResolvedSuburb)
    assert result.name == "LITTLE MOUNTAIN"
    assert result.postcode == "4551"
    assert result.state == "QLD"
    assert result.oth_slug == "little-mountain-4551"
    # Persisted
    assert result.id is not None


async def test_resolve_multi_match_returns_candidate_list(session):
    async with _mock_client_returning(_fixture("richmond.json")) as client:
        result = await resolve("Richmond", session=session, client=client)

    assert isinstance(result, list)
    assert all(isinstance(m, Match) for m in result)
    assert len(result) == 7  # NSW×2, QLD×2, SA, TAS, VIC


async def test_resolve_disambiguates_via_state(session):
    async with _mock_client_returning(_fixture("richmond.json")) as client:
        result = await resolve("Richmond", session=session, client=client, state="VIC")

    assert isinstance(result, ResolvedSuburb)
    assert result.state == "VIC"
    assert result.postcode == "3121"


async def test_resolve_cached_does_not_call_oth(session):
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_fixture("little_mountain.json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await resolve("Little Mountain", session=session, client=client)
        second = await resolve("Little Mountain", session=session, client=client)

    assert call_count == 1, "second call should hit cache, not OTH"
    assert isinstance(first, ResolvedSuburb)
    assert isinstance(second, ResolvedSuburb)
    assert first.id == second.id


async def test_resolve_no_match_raises(session):
    empty = {"content": [], "totalElements": 0}
    async with _mock_client_returning(empty) as client:
        with pytest.raises(NoMatchError):
            await resolve("Nonexistentville", session=session, client=client)


async def test_resolve_anti_bot_response_raises_unavailable(session):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AutocompleteUnavailableError):
            await resolve("Little Mountain", session=session, client=client)


async def test_resolve_empty_name_raises_value_error(session):
    with pytest.raises(ValueError):
        await resolve("   ", session=session)
