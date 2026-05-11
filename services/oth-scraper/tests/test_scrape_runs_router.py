"""Integration tests for GET /scrape-runs endpoints.

Happy-path coverage:
  - GET /scrape-runs            (list, filter by list_id, filter by status)
  - GET /scrape-runs/{id}       (detail with job_counts rollup)
  - GET /scrape-runs/{id}/jobs  (child jobs)
  - 404 cases
"""
from datetime import datetime, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.api.app import app
from oth_scraper.db.engine import get_db, get_session_factory
from oth_scraper.db.models import ScrapeJob, ScrapeList, ScrapeListSuburb, ScrapeRun, Suburb


@pytest_asyncio.fixture
async def api_client(session_factory: async_sessionmaker[AsyncSession]):
    async def _override_get_db():
        async with session_factory() as s:
            yield s

    def _override_get_session_factory():
        return session_factory

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = _override_get_session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ------------------------------------------------------------------ #
# helpers                                                             #
# ------------------------------------------------------------------ #


async def _seed_suburb(
    factory: async_sessionmaker[AsyncSession],
    name: str = "Nambour",
    postcode: str = "4560",
) -> int:
    async with factory() as s:
        async with s.begin():
            row = Suburb(
                name=name,
                postcode=postcode,
                state="QLD",
                oth_slug=f"{name.lower()}-qld-{postcode}",
            )
            s.add(row)
            await s.flush()
            return row.id


async def _seed_list_with_suburbs(
    factory: async_sessionmaker[AsyncSession],
    *,
    suburb_ids: list[int],
) -> int:
    async with factory() as s:
        async with s.begin():
            row = ScrapeList(
                name="run-router-test",
                description=None,
                filters={},
                cron_schedule=None,
            )
            s.add(row)
            await s.flush()
            list_id = row.id
            for sid in suburb_ids:
                s.add(ScrapeListSuburb(scrape_list_id=list_id, suburb_id=sid))
            await s.flush()
            return list_id


async def _seed_run(
    factory: async_sessionmaker[AsyncSession],
    *,
    list_id: int | None = None,
    status: str = "running",
    trigger_source: str = "api",
) -> int:
    async with factory() as s:
        async with s.begin():
            row = ScrapeRun(
                scrape_list_id=list_id,
                trigger_source=trigger_source,
                filters_snapshot={},
                status=status,
            )
            s.add(row)
            await s.flush()
            return row.id


async def _seed_job(
    factory: async_sessionmaker[AsyncSession],
    *,
    run_id: int,
    status: str = "queued",
    category: str = "forsale",
) -> int:
    completed_at = None
    if status in ("succeeded", "failed", "deadletter"):
        completed_at = datetime.now(timezone.utc)
    async with factory() as s:
        async with s.begin():
            row = ScrapeJob(
                run_id=run_id,
                category=category,
                filters={},
                status=status,
                attempts=0,
                completed_at=completed_at,
            )
            s.add(row)
            await s.flush()
            return row.id


# ------------------------------------------------------------------ #
# GET /scrape-runs                                                    #
# ------------------------------------------------------------------ #


async def test_list_runs_returns_newest_first(api_client, session_factory):
    run_id1 = await _seed_run(session_factory, status="succeeded")
    run_id2 = await _seed_run(session_factory, status="running")

    r = await api_client.get("/scrape-runs")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    # newest first — run_id2 was inserted after run_id1
    ids = [row["id"] for row in rows]
    assert ids.index(run_id2) < ids.index(run_id1)


async def test_list_runs_filter_by_list_id(api_client, session_factory):
    sub_id = await _seed_suburb(session_factory, "Maroochydore", "4558")
    list_id = await _seed_list_with_suburbs(session_factory, suburb_ids=[sub_id])
    run_id = await _seed_run(session_factory, list_id=list_id)
    # Another run not linked to the list
    await _seed_run(session_factory)

    r = await api_client.get(f"/scrape-runs?list_id={list_id}")
    assert r.status_code == 200
    rows = r.json()
    assert all(row["scrape_list_id"] == list_id for row in rows)
    assert any(row["id"] == run_id for row in rows)


async def test_list_runs_filter_by_status(api_client, session_factory):
    await _seed_run(session_factory, status="succeeded")
    await _seed_run(session_factory, status="running")
    await _seed_run(session_factory, status="failed")

    r = await api_client.get("/scrape-runs?status=succeeded")
    assert r.status_code == 200
    rows = r.json()
    assert all(row["status"] == "succeeded" for row in rows)
    assert len(rows) >= 1


async def test_list_runs_invalid_status_422(api_client):
    r = await api_client.get("/scrape-runs?status=bogus")
    assert r.status_code == 422


# ------------------------------------------------------------------ #
# GET /scrape-runs/{id}                                              #
# ------------------------------------------------------------------ #


async def test_get_run_includes_job_counts(api_client, session_factory):
    run_id = await _seed_run(session_factory)
    await _seed_job(session_factory, run_id=run_id, status="queued")
    await _seed_job(session_factory, run_id=run_id, status="running")
    await _seed_job(session_factory, run_id=run_id, status="succeeded")
    await _seed_job(session_factory, run_id=run_id, status="failed")
    await _seed_job(session_factory, run_id=run_id, status="deadletter")

    r = await api_client.get(f"/scrape-runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == run_id
    counts = body["job_counts"]
    assert counts["queued"] == 1
    assert counts["running"] == 1
    assert counts["succeeded"] == 1
    assert counts["failed"] == 1
    assert counts["deadletter"] == 1


async def test_get_run_empty_job_counts(api_client, session_factory):
    """A run with no child jobs returns an empty job_counts dict."""
    run_id = await _seed_run(session_factory)
    r = await api_client.get(f"/scrape-runs/{run_id}")
    assert r.status_code == 200
    assert r.json()["job_counts"] == {}


async def test_get_run_404(api_client):
    r = await api_client.get("/scrape-runs/999999")
    assert r.status_code == 404


# ------------------------------------------------------------------ #
# GET /scrape-runs/{id}/jobs                                         #
# ------------------------------------------------------------------ #


async def test_list_run_jobs_returns_child_jobs(api_client, session_factory):
    run_id = await _seed_run(session_factory)
    job_id1 = await _seed_job(
        session_factory, run_id=run_id, status="queued", category="forsale"
    )
    job_id2 = await _seed_job(
        session_factory, run_id=run_id, status="succeeded", category="forrent"
    )

    r = await api_client.get(f"/scrape-runs/{run_id}/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 2
    ids = {j["id"] for j in jobs}
    assert ids == {job_id1, job_id2}
    assert all(j["run_id"] == run_id for j in jobs)


async def test_list_run_jobs_only_returns_own_children(
    api_client, session_factory
):
    """Jobs from a different run must not appear."""
    run_id_a = await _seed_run(session_factory)
    run_id_b = await _seed_run(session_factory)
    job_a = await _seed_job(session_factory, run_id=run_id_a, status="queued")
    job_b = await _seed_job(session_factory, run_id=run_id_b, status="queued")

    r = await api_client.get(f"/scrape-runs/{run_id_a}/jobs")
    assert r.status_code == 200
    ids = {j["id"] for j in r.json()}
    assert job_a in ids
    assert job_b not in ids


async def test_list_run_jobs_404_for_unknown_run(api_client):
    r = await api_client.get("/scrape-runs/999999/jobs")
    assert r.status_code == 404


# ------------------------------------------------------------------ #
# POST /scrape-lists/{id}/run creates scrape_run row                 #
# ------------------------------------------------------------------ #


async def test_run_endpoint_creates_run_with_api_trigger_source(
    api_client, session_factory
):
    sub_id = await _seed_suburb(session_factory, "Caloundra", "4551")
    list_id = await _seed_list_with_suburbs(session_factory, suburb_ids=[sub_id])

    r = await api_client.post(f"/scrape-lists/{list_id}/run")
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    run_id = body["run_id"]
    assert run_id > 0
    assert body["count"] == 3

    # Verify run row persisted.
    async with session_factory() as s:
        run = await s.get(ScrapeRun, run_id)
        assert run is not None
        assert run.trigger_source == "api"
        assert run.scrape_list_id == list_id
        assert run.status == "running"


async def test_run_endpoint_creates_run_with_cli_trigger_source(
    api_client, session_factory
):
    sub_id = await _seed_suburb(session_factory, "Buderim", "4556")
    list_id = await _seed_list_with_suburbs(session_factory, suburb_ids=[sub_id])

    r = await api_client.post(
        f"/scrape-lists/{list_id}/run",
        json={"trigger_source": "cli"},
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]

    async with session_factory() as s:
        run = await s.get(ScrapeRun, run_id)
        assert run is not None
        assert run.trigger_source == "cli"


# ------------------------------------------------------------------ #
# OpenAPI surface                                                     #
# ------------------------------------------------------------------ #


async def test_openapi_documents_scrape_run_endpoints(api_client):
    r = await api_client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/scrape-runs" in paths
    assert "/scrape-runs/{run_id}" in paths
    assert "/scrape-runs/{run_id}/jobs" in paths
