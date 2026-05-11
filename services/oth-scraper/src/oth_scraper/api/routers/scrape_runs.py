"""REST endpoints for scrape-run inspection.

Three read endpoints:
  GET /scrape-runs                    — list runs (filter by list_id, status)
  GET /scrape-runs/{id}               — run detail with per-status job counts
  GET /scrape-runs/{id}/jobs          — child jobs for a run
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.engine import get_db
from oth_scraper.db.models.scrape_job import ScrapeJob
from oth_scraper.db.models.scrape_run import RUN_STATUS_VALUES, ScrapeRun

router = APIRouter()


class ScrapeRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scrape_list_id: int | None
    triggered_at: datetime
    completed_at: datetime | None
    status: str
    trigger_source: str
    filters_snapshot: dict[str, Any]
    retried_from_run_id: int | None
    created_at: datetime


class ScrapeRunDetail(ScrapeRunRead):
    """Run detail with per-status job counts rollup."""

    job_counts: dict[str, int]


class JobRead(BaseModel):
    """Slim job representation returned from /scrape-runs/{id}/jobs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    scrape_list_id: int | None
    suburb_id: int | None
    category: str
    filters: dict[str, Any]
    status: str
    attempts: int
    last_error_class: str | None
    last_error_message: str | None
    claimed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@router.get("", response_model=list[ScrapeRunRead])
async def list_runs(
    list_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[ScrapeRunRead]:
    if status is not None and status not in RUN_STATUS_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {list(RUN_STATUS_VALUES)}",
        )
    stmt = select(ScrapeRun).order_by(ScrapeRun.triggered_at.desc())
    if list_id is not None:
        stmt = stmt.where(ScrapeRun.scrape_list_id == list_id)
    if status is not None:
        stmt = stmt.where(ScrapeRun.status == status)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [ScrapeRunRead.model_validate(r) for r in rows]


@router.get("/{run_id}", response_model=ScrapeRunDetail)
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_db),
) -> ScrapeRunDetail:
    row = await session.get(ScrapeRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    # Per-status counts rollup — single aggregate query.
    counts_stmt = (
        select(ScrapeJob.status, func.count().label("n"))
        .where(ScrapeJob.run_id == run_id)
        .group_by(ScrapeJob.status)
    )
    counts_rows = (await session.execute(counts_stmt)).all()
    job_counts: dict[str, int] = {r.status: r.n for r in counts_rows}

    base = ScrapeRunRead.model_validate(row)
    return ScrapeRunDetail(**base.model_dump(), job_counts=job_counts)


@router.get("/{run_id}/jobs", response_model=list[JobRead])
async def list_run_jobs(
    run_id: int,
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[JobRead]:
    # Verify the run exists first.
    run = await session.get(ScrapeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    stmt = (
        select(ScrapeJob)
        .where(ScrapeJob.run_id == run_id)
        .order_by(ScrapeJob.id)
    )
    if status is not None:
        stmt = stmt.where(ScrapeJob.status == status)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [JobRead.model_validate(r) for r in rows]
