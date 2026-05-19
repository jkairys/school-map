"""REST endpoints for inspecting properties."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.db.engine import get_db
from listings_scraper.db.models.property import Property

router = APIRouter()


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_property_id: str | None
    formatted_address: str
    postcode: str
    suburb_id: int
    first_seen_at: datetime


@router.get("", response_model=list[PropertyRead])
async def list_properties(
    suburb: int | None = Query(
        default=None, description="Filter by suburb_id."
    ),
    postcode: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[PropertyRead]:
    stmt = select(Property).order_by(Property.id.desc())
    if suburb is not None:
        stmt = stmt.where(Property.suburb_id == suburb)
    if postcode is not None:
        stmt = stmt.where(Property.postcode == postcode)
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [PropertyRead.model_validate(r) for r in rows]
