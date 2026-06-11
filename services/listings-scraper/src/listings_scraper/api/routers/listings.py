"""REST endpoints for inspecting listings and their snapshots."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from listings_scraper.db.engine import get_db
from listings_scraper.db.models.listing import LISTING_CATEGORY_VALUES, Listing
from listings_scraper.db.models.listing_snapshot import ListingSnapshot

router = APIRouter()


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    observed_at: datetime
    price: int | None
    title: str | None
    blurb: str | None
    bedrooms: int | None
    bathrooms: int | None
    parking: int | None
    land_size_sqm: int | None
    property_type: str | None
    status: str | None
    raw_payload: dict[str, Any]
    changed_fields: list[str]


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    suburb_id: int
    category: str
    external_listing_id: str | None
    agent_name: str | None
    agency_name: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    closure_reason: str | None


class ListingDetail(ListingRead):
    latest_snapshot: SnapshotRead | None


@router.get("", response_model=list[ListingRead])
async def list_listings(
    suburb: int | None = Query(
        default=None, description="Filter by suburb_id."
    ),
    category: str | None = Query(default=None),
    active: bool | None = Query(
        default=None,
        description="When true, return only listings with closed_at IS NULL.",
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[ListingRead]:
    if category is not None and category not in LISTING_CATEGORY_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"category must be one of {list(LISTING_CATEGORY_VALUES)}",
        )
    stmt = select(Listing).order_by(Listing.id.desc())
    if suburb is not None:
        stmt = stmt.where(Listing.suburb_id == suburb)
    if category is not None:
        stmt = stmt.where(Listing.category == category)
    if active:
        stmt = stmt.where(Listing.closed_at.is_(None))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [ListingRead.model_validate(r) for r in rows]


@router.get("/{listing_id}", response_model=ListingDetail)
async def get_listing(
    listing_id: int, session: AsyncSession = Depends(get_db)
) -> ListingDetail:
    row = await session.get(Listing, listing_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"listing {listing_id} not found"
        )
    snap_stmt = (
        select(ListingSnapshot)
        .where(ListingSnapshot.listing_id == listing_id)
        .order_by(ListingSnapshot.observed_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
    )
    latest = (await session.execute(snap_stmt)).scalar_one_or_none()
    base = ListingRead.model_validate(row).model_dump()
    return ListingDetail(
        **base,
        latest_snapshot=(
            SnapshotRead.model_validate(latest) if latest is not None else None
        ),
    )


@router.get("/{listing_id}/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    listing_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[SnapshotRead]:
    listing = await session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(
            status_code=404, detail=f"listing {listing_id} not found"
        )
    stmt = (
        select(ListingSnapshot)
        .where(ListingSnapshot.listing_id == listing_id)
        .order_by(ListingSnapshot.observed_at.asc(), ListingSnapshot.id.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [SnapshotRead.model_validate(r) for r in rows]
