"""REST endpoints for inspecting scrape jobs."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.engine import get_db
from oth_scraper.db.models.scrape_job import JOB_STATUS_VALUES, ScrapeJob

router = APIRouter()


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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


@router.get("", response_model=list[JobRead])
async def list_jobs(
    status: str | None = Query(default=None),
    list_id: int | None = Query(default=None, alias="list_id"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[JobRead]:
    if status is not None and status not in JOB_STATUS_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {list(JOB_STATUS_VALUES)}",
        )
    stmt = select(ScrapeJob).order_by(ScrapeJob.id.desc())
    if status is not None:
        stmt = stmt.where(ScrapeJob.status == status)
    if list_id is not None:
        stmt = stmt.where(ScrapeJob.scrape_list_id == list_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [JobRead.model_validate(r) for r in rows]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: int, session: AsyncSession = Depends(get_db)
) -> JobRead:
    row = await session.get(ScrapeJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return JobRead.model_validate(row)
