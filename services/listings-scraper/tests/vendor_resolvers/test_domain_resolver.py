"""Tests for DomainSuburbResolver.

Uses an in-memory async SQLite DB (same pattern as test_suburb_resolver.py)
to exercise the DB persistence without a Postgres testcontainer.

Key properties verified:
- Slug is correctly computed as <name-hyphenated>-<state-lower>-<postcode>
- Cache hit returns the same row without inserting a duplicate
- Missing postcode or state raises SuburbResolutionError
- source=Vendor.DOMAIN is set on all persisted rows
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from listings_scraper.db.models.suburb import Suburb
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_resolvers.domain.resolver import (
    DomainSuburbResolver,
    SuburbResolutionError,
    _build_slug,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """In-memory async SQLite session for resolver tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Suburb.__table__.create(c))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        yield s
    await engine.dispose()


# ---------------------------------------------------------------------------
# Slug computation — pure function, no DB
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,state,postcode,expected",
    [
        ("Paddington", "QLD", "4064", "paddington-qld-4064"),
        ("Little Mountain", "QLD", "4551", "little-mountain-qld-4551"),
        ("South Yarra", "VIC", "3141", "south-yarra-vic-3141"),
        ("North Sydney", "NSW", "2060", "north-sydney-nsw-2060"),
        # State normalised to lowercase in slug
        ("Paddington", "qld", "4064", "paddington-qld-4064"),
    ],
)
def test_build_slug(name: str, state: str, postcode: str, expected: str) -> None:
    assert _build_slug(name, state, postcode) == expected


# ---------------------------------------------------------------------------
# Resolver — happy path
# ---------------------------------------------------------------------------


async def test_resolve_paddington_qld_inserts_row(session: AsyncSession) -> None:
    """Resolving Paddington QLD 4064 inserts a row with the correct slug."""
    resolver = DomainSuburbResolver()
    result = await resolver.resolve("Paddington", db=session, postcode="4064", state="QLD")
    assert result.slug == "paddington-qld-4064"
    assert result.source is Vendor.DOMAIN
    assert result.name == "Paddington"
    assert result.postcode == "4064"
    assert result.state == "QLD"
    assert result.id is not None


async def test_resolve_little_mountain_slug(session: AsyncSession) -> None:
    """Multi-word suburb name gets hyphens in slug."""
    resolver = DomainSuburbResolver()
    result = await resolver.resolve("Little Mountain", db=session, postcode="4551", state="QLD")
    assert result.slug == "little-mountain-qld-4551"


async def test_resolve_returns_cached_on_second_call(session: AsyncSession) -> None:
    """Resolving the same suburb twice returns the cached row (no duplicate insert)."""
    resolver = DomainSuburbResolver()
    first = await resolver.resolve("Paddington", db=session, postcode="4064", state="QLD")
    second = await resolver.resolve("Paddington", db=session, postcode="4064", state="QLD")
    assert first.id == second.id, "Second call should return the cached row"


async def test_resolve_cache_hit_is_case_insensitive(session: AsyncSession) -> None:
    """Case-insensitive name match should hit the cache."""
    resolver = DomainSuburbResolver()
    first = await resolver.resolve("Paddington", db=session, postcode="4064", state="QLD")
    second = await resolver.resolve("paddington", db=session, postcode="4064", state="QLD")
    assert first.id == second.id


async def test_resolve_source_is_domain(session: AsyncSession) -> None:
    """Persisted suburb must have source=Vendor.DOMAIN."""
    resolver = DomainSuburbResolver()
    result = await resolver.resolve("Paddington", db=session, postcode="4064", state="QLD")
    assert result.source is Vendor.DOMAIN


# ---------------------------------------------------------------------------
# Resolver — error cases
# ---------------------------------------------------------------------------


async def test_resolve_without_postcode_raises(session: AsyncSession) -> None:
    """Missing postcode raises SuburbResolutionError."""
    resolver = DomainSuburbResolver()
    with pytest.raises(SuburbResolutionError, match="requires postcode and state"):
        await resolver.resolve("Paddington", db=session, state="QLD")


async def test_resolve_without_state_raises(session: AsyncSession) -> None:
    """Missing state raises SuburbResolutionError."""
    resolver = DomainSuburbResolver()
    with pytest.raises(SuburbResolutionError, match="requires postcode and state"):
        await resolver.resolve("Paddington", db=session, postcode="4064")


async def test_resolve_without_either_raises(session: AsyncSession) -> None:
    """Missing both postcode and state raises SuburbResolutionError."""
    resolver = DomainSuburbResolver()
    with pytest.raises(SuburbResolutionError):
        await resolver.resolve("Paddington", db=session)


# ---------------------------------------------------------------------------
# DomainSuburbResolver class-level assertions
# ---------------------------------------------------------------------------


def test_resolver_source_class_var() -> None:
    """DomainSuburbResolver.source must be Vendor.DOMAIN."""
    assert DomainSuburbResolver.source is Vendor.DOMAIN
