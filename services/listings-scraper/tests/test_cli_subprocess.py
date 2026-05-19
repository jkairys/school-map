"""Integration tests: drive the `oth` CLI as a subprocess against a running api.

The api is launched as a child process (uvicorn) bound to a free loopback
port and pointed at the same Postgres testcontainer the rest of the suite
uses. Each test truncates the schema first so it's order-independent.

The tests intentionally exercise the HTTP path end-to-end — they never
import the CLI command impls or the api app directly, because the whole
point of issue 13 is to verify the CLI ↔ REST seam.

Disambiguation: rather than wire pexpect, we pre-seed the `suburb` table
so the resolver's cache lookup short-circuits the OTH autocomplete call.
That's enough to cover the non-TTY happy path; the TTY prompt logic is
exercised by the impl-level paths in code review.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from listings_scraper.db.models import (
    Listing,
    ListingSnapshot,
    Property,
    Suburb,
)


_TRUNCATE_TABLES = (
    "listing_snapshot",
    "listing",
    "property",
    "scrape_list_suburb",
    "scrape_list",
    "scrape_job",
    "suburb",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture(scope="session")
async def schema_ready(postgres_url: str) -> AsyncEngine:
    """Build the schema once for the session.

    Per-test isolation is handled by `clean_db` (TRUNCATE before each
    test). Reusing a single api subprocess across the whole module keeps
    test wall time reasonable.
    """
    from listings_scraper.db.engine import Base
    from listings_scraper.db import models  # noqa: F401  -- registers models

    engine = create_async_engine(postgres_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.fixture(scope="session")
def api_subprocess(
    postgres_url: str, schema_ready: AsyncEngine
) -> Iterator[str]:
    """Start uvicorn against the testcontainer DB; yield the base URL."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "OTH_DATABASE_URL": postgres_url,
            "OTH_API_HOST": "127.0.0.1",
            "OTH_API_PORT": str(port),
            "PYTHONPATH": str(repo_root / "src"),
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "listings_scraper.api.entrypoint"],
        env=env,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # Poll /health for up to 30s; fail loudly if the api never came up.
        deadline = time.monotonic() + 30.0
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode() if proc.stdout else ""
                raise RuntimeError(
                    f"api subprocess exited early (rc={proc.returncode}):\n{out}"
                )
            try:
                r = httpx.get(f"{base_url}/health", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError as e:
                last_err = e
            time.sleep(0.2)
        else:
            raise RuntimeError(
                f"api never became healthy at {base_url}; last error: {last_err}"
            )
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest_asyncio.fixture
async def session_factory_for_test(
    postgres_url: str,
) -> async_sessionmaker:
    """Per-test session factory bound to its own engine.

    Function-scoped so the engine binds to the same event loop as the test.
    """
    engine = create_async_engine(postgres_url, future=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(
    api_subprocess: str, session_factory_for_test: async_sessionmaker
) -> None:
    """TRUNCATE every table before each test to keep the api process clean."""
    async with session_factory_for_test() as s:
        async with s.begin():
            await s.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(_TRUNCATE_TABLES)} "
                    "RESTART IDENTITY CASCADE"
                )
            )


def run_cli(*args: str, base_url: str) -> subprocess.CompletedProcess:
    """Invoke the `oth` CLI as a subprocess and capture stdout/stderr."""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["OTH_SCRAPER_BASE_URL"] = base_url
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "listings_scraper.cli.main", *args],
        env=env,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
    )


# --- helpers ---


async def _seed_suburb(
    factory: async_sessionmaker,
    *,
    name: str = "Paddington",
    postcode: str = "4064",
    state: str = "QLD",
) -> int:
    async with factory() as s:
        async with s.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state=state,
                oth_slug=f"{name.lower().replace(' ', '-')}-{postcode}",
            )
            s.add(row)
            await s.flush()
            return row.id


# --- tests ---


async def test_suburb_resolve_uses_cached_row(
    api_subprocess, session_factory_for_test
):
    sub_id = await _seed_suburb(session_factory_for_test)

    res = run_cli(
        "suburb",
        "resolve",
        "Paddington",
        "--postcode",
        "4064",
        "--state",
        "QLD",
        base_url=api_subprocess,
    )
    assert res.returncode == 0, res.stderr
    assert "Paddington, QLD 4064" in res.stdout
    assert "paddington-4064" in res.stdout
    assert f"id: {sub_id}" in res.stdout


async def test_list_lifecycle_create_add_run_rm(
    api_subprocess, session_factory_for_test, tmp_path
):
    sub_id = await _seed_suburb(session_factory_for_test)

    # create with --filters @file.json
    filters_file = tmp_path / "filters.json"
    filters_file.write_text('{"beds_min": 3, "price_max": 1500000}')
    res = run_cli(
        "list",
        "create",
        "myl",
        "--filters",
        f"@{filters_file}",
        base_url=api_subprocess,
    )
    assert res.returncode == 0, res.stderr
    assert "#1 myl" in res.stdout
    assert "beds_min" in res.stdout

    # ls
    ls = run_cli("list", "ls", base_url=api_subprocess)
    assert ls.returncode == 0, ls.stderr
    assert "myl" in ls.stdout
    assert "(0 suburbs)" in ls.stdout

    # add-suburb resolves via cache (no OTH call thanks to seeded row)
    add = run_cli(
        "list",
        "add-suburb",
        "myl",
        "Paddington",
        "--postcode",
        "4064",
        "--state",
        "QLD",
        base_url=api_subprocess,
    )
    assert add.returncode == 0, add.stderr
    assert f"Added: Paddington, QLD 4064 → list 1" in add.stdout

    # show by name
    show = run_cli("list", "show", "myl", base_url=api_subprocess)
    assert show.returncode == 0, show.stderr
    assert f"[{sub_id}] Paddington, QLD 4064" in show.stdout

    # run by name
    run = run_cli("list", "run", "myl", base_url=api_subprocess)
    assert run.returncode == 0, run.stderr
    assert "Enqueued 3 jobs for list 1" in run.stdout

    # rm-suburb by suburb name
    rms = run_cli(
        "list", "rm-suburb", "myl", "Paddington", base_url=api_subprocess
    )
    assert rms.returncode == 0, rms.stderr
    assert f"Removed suburb {sub_id} from list 1" in rms.stdout

    # rm by name
    rm = run_cli("list", "rm", "myl", base_url=api_subprocess)
    assert rm.returncode == 0, rm.stderr
    assert "Deleted scrape list 1" in rm.stdout


async def test_jobs_ls_and_show(api_subprocess, session_factory_for_test):
    await _seed_suburb(session_factory_for_test)

    # set up via the CLI itself so the data is created on the same DB
    assert (
        run_cli("list", "create", "jl", base_url=api_subprocess).returncode == 0
    )
    assert (
        run_cli(
            "list",
            "add-suburb",
            "jl",
            "Paddington",
            "--postcode",
            "4064",
            "--state",
            "QLD",
            base_url=api_subprocess,
        ).returncode
        == 0
    )
    assert run_cli("list", "run", "jl", base_url=api_subprocess).returncode == 0

    ls = run_cli(
        "jobs", "ls", "--list", "jl", "--status", "queued",
        base_url=api_subprocess,
    )
    assert ls.returncode == 0, ls.stderr
    # Three jobs (forsale, forrent, recentlysold) for the one suburb.
    queued_lines = [l for l in ls.stdout.splitlines() if "queued" in l]
    assert len(queued_lines) == 3

    show = run_cli("jobs", "show", "1", base_url=api_subprocess)
    assert show.returncode == 0, show.stderr
    assert "#1 queued" in show.stdout
    assert "category:" in show.stdout

    # 404 path
    miss = run_cli("jobs", "show", "99999", base_url=api_subprocess)
    assert miss.returncode == 1
    assert "Not found" in miss.stderr


async def test_listings_ls_show_history(
    api_subprocess, session_factory_for_test
):
    sub_id = await _seed_suburb(session_factory_for_test)
    async with session_factory_for_test() as s:
        async with s.begin():
            prop = Property(
                oth_property_id="P-1",
                formatted_address="1 Main St",
                postcode="4064",
                suburb_id=sub_id,
            )
            s.add(prop)
            await s.flush()
            listing = Listing(
                property_id=prop.id,
                suburb_id=sub_id,
                category="forsale",
                oth_listing_id="L-1",
                agent_name="Joe",
                agency_name="Acme",
            )
            s.add(listing)
            await s.flush()
            for price, status_ in ((800000, "available"), (850000, "available")):
                s.add(
                    ListingSnapshot(
                        listing_id=listing.id,
                        observed_at=datetime.now(timezone.utc),
                        price=price,
                        title="Lovely",
                        blurb=None,
                        bedrooms=3,
                        bathrooms=2,
                        parking=1,
                        land_size_sqm=600,
                        property_type="House",
                        status=status_,
                        raw_payload={"id": "raw"},
                        changed_fields=["price"],
                    )
                )
            listing_id = listing.id

    ls = run_cli(
        "listings", "ls",
        "--suburb", str(sub_id),
        "--category", "forsale",
        "--active",
        base_url=api_subprocess,
    )
    assert ls.returncode == 0, ls.stderr
    assert f"#     {listing_id}" in ls.stdout or f"#{listing_id:>6}" in ls.stdout
    assert "forsale" in ls.stdout

    show = run_cli(
        "listings", "show", str(listing_id), base_url=api_subprocess
    )
    assert show.returncode == 0, show.stderr
    assert f"#{listing_id} forsale" in show.stdout
    assert "latest snapshot:" in show.stdout
    assert "price: 850000" in show.stdout

    history = run_cli(
        "listings", "history", str(listing_id), base_url=api_subprocess
    )
    assert history.returncode == 0, history.stderr
    history_lines = [
        l for l in history.stdout.splitlines() if "price=" in l
    ]
    assert len(history_lines) == 2


async def test_filters_inline_json(api_subprocess, session_factory_for_test):
    res = run_cli(
        "list", "create", "ij", "--filters", '{"beds_min": 4}',
        base_url=api_subprocess,
    )
    assert res.returncode == 0, res.stderr
    show = run_cli("list", "show", "ij", base_url=api_subprocess)
    assert show.returncode == 0
    assert "'beds_min': 4" in show.stdout


async def test_resolve_list_id_404(api_subprocess):
    res = run_cli("list", "show", "9999", base_url=api_subprocess)
    assert res.returncode == 1
    assert "Not found" in res.stderr


async def test_unreachable_api_exits_non_zero(monkeypatch):
    res = run_cli(
        "list", "ls",
        base_url="http://127.0.0.1:1",  # nothing here
    )
    assert res.returncode == 2
    assert "Could not reach api" in res.stderr
