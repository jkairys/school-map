"""Shared test fixtures.

The Postgres test container is the new test pattern for this service —
issue 08 (the reconciler) is expected to adopt the same shape.

Layering:
- container: session-scoped (slow to start)
- engine + session_factory: function-scoped (asyncpg connections must bind
  to the same event loop that drives the test, and pytest-asyncio creates
  a fresh loop per test)
- schema is built via Base.metadata.create_all on first connect; per-test
  TRUNCATE keeps tests independent without rebuilding the schema.
"""
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def _docker_available() -> bool:
    try:
        import docker  # type: ignore[import-untyped]
    except Exception:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


_HAS_DOCKER = _docker_available()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    if not _HAS_DOCKER:
        pytest.skip("Docker not available — Postgres testcontainer cannot start")

    from testcontainers.postgres import PostgresContainer

    # postgis image required: the `property.location` column is
    # geography(Point, 4326) and Base.metadata.create_all builds it on
    # every test engine. Plain postgres would error on the Geography type.
    with PostgresContainer("postgis/postgis:16-3.4-alpine") as pg:
        raw_url = pg.get_connection_url()
        async_url = raw_url.replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        ).replace("postgresql://", "postgresql+asyncpg://")
        yield async_url


# Tables we TRUNCATE between tests. Listed children-first so the FK CASCADE
# isn't load-bearing. Geography columns on `property` need the postgis
# extension; the engine fixture enables it on first connect before
# Base.metadata.create_all runs.
_TRUNCATE_TABLES = (
    "listing_snapshot",
    "listing",
    "property",
    "scrape_list_suburb",
    "scrape_job",
    "scrape_run",
    "scrape_list",
    "suburb",
)


@pytest_asyncio.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    # Importing models registers them on Base.metadata.
    from oth_scraper.db.engine import Base
    from oth_scraper.db import models  # noqa: F401

    engine = create_async_engine(postgres_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
        # Keep tests independent; safe because the engine is function-scoped.
        # CASCADE handles every FK; RESTART IDENTITY so id assertions are
        # stable run to run.
        await conn.execute(
            text(
                f"TRUNCATE TABLE {', '.join(_TRUNCATE_TABLES)} "
                "RESTART IDENTITY CASCADE"
            )
        )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
