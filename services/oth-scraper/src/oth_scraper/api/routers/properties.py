"""REST endpoints for inspecting properties."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.engine import get_db
from oth_scraper.db.models.listing import Listing
from oth_scraper.db.models.listing_snapshot import ListingSnapshot
from oth_scraper.db.models.property import Property

router = APIRouter()

SortOrder = Literal["price_desc", "price_asc", "observed_at_desc"]


class SnapshotSummary(BaseModel):
    """Minimal latest-snapshot summary attached to each property/listing row."""

    model_config = ConfigDict(from_attributes=True)

    price: int | None
    observed_at: datetime
    category: str
    status: str | None


class PropertyWithRollup(BaseModel):
    """Property row with latest-snapshot rollup fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    oth_property_id: str | None
    formatted_address: str
    postcode: str
    suburb_id: int
    first_seen_at: datetime
    latest_price: int | None
    latest_observed_at: datetime | None
    latest_category: str | None
    latest_status: str | None


class ListingWithSnapshot(BaseModel):
    """Listing row with its latest snapshot summary (or None)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    suburb_id: int
    category: str
    oth_listing_id: str | None
    agent_name: str | None
    agency_name: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    closure_reason: str | None
    latest_snapshot: SnapshotSummary | None


class PropertyDetail(BaseModel):
    """Property detail response: property + all listing campaigns."""

    property: "PropertyRead"
    listings: list[ListingWithSnapshot]


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    oth_property_id: str | None
    formatted_address: str
    postcode: str
    suburb_id: int
    first_seen_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_snapshot_lateral(session: AsyncSession):
    """
    Build a lateral subquery that returns the latest listing_snapshot row
    for a given listing. Used as a correlated subquery in the property list
    rollup.

    We use a DISTINCT ON approach via a window function CTE so the whole
    property-list query is one SQL statement.
    """
    # This is used as a building block only; the actual query is built inline
    # in list_properties using raw SQL for clarity.
    pass  # Not used as a standalone helper — query is inline.


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PropertyWithRollup])
async def list_properties(
    suburb: int | None = Query(
        default=None, description="Filter by suburb_id."
    ),
    postcode: str | None = Query(default=None),
    search: str | None = Query(
        default=None,
        description="Filter by formatted_address ILIKE %%search%%.",
    ),
    sort: SortOrder = Query(
        default="observed_at_desc",
        description=(
            "Sort order: price_desc, price_asc, or observed_at_desc (default)."
        ),
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> list[PropertyWithRollup]:
    """List properties with latest-snapshot rollup.

    The rollup (latest_price, latest_observed_at, latest_category,
    latest_status) is computed in a single SQL query using a lateral join
    via DISTINCT ON — no per-row Python fetches.

    Sorting by price uses the latest snapshot's price. Properties with no
    snapshots sort last.
    """
    # Build the query as raw SQL so we can use DISTINCT ON cleanly.
    # The lateral CTE picks the single most-recent snapshot per listing,
    # then we pick the most-recent snapshot across all listings per property.
    #
    # Strategy:
    #   1. latest_snap CTE: DISTINCT ON (listing_id) ordered by observed_at DESC
    #      → one row per listing.
    #   2. best_snap CTE: DISTINCT ON (property_id) from latest_snap joined
    #      with listing, ordered by observed_at DESC → one row per property.
    #   3. Main SELECT joins property LEFT JOIN best_snap.

    filters: list[str] = []
    params: dict = {"limit": limit, "offset": offset}

    if suburb is not None:
        filters.append("p.suburb_id = :suburb_id")
        params["suburb_id"] = suburb

    if postcode is not None:
        filters.append("p.postcode = :postcode")
        params["postcode"] = postcode

    if search is not None:
        filters.append("p.formatted_address ILIKE :search")
        params["search"] = f"%{search}%"

    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    sort_expr = {
        "price_desc": "bs.price DESC NULLS LAST, p.id DESC",
        "price_asc": "bs.price ASC NULLS LAST, p.id DESC",
        "observed_at_desc": "bs.observed_at DESC NULLS LAST, p.id DESC",
    }[sort]

    sql = f"""
        WITH latest_snap AS (
            SELECT DISTINCT ON (ls.listing_id)
                ls.listing_id,
                ls.price,
                ls.observed_at,
                ls.status
            FROM listing_snapshot ls
            ORDER BY ls.listing_id, ls.observed_at DESC, ls.id DESC
        ),
        best_snap AS (
            SELECT DISTINCT ON (l.property_id)
                l.property_id,
                l.category,
                lsn.price,
                lsn.observed_at,
                lsn.status
            FROM listing l
            JOIN latest_snap lsn ON lsn.listing_id = l.id
            ORDER BY l.property_id, lsn.observed_at DESC
        )
        SELECT
            p.id,
            p.oth_property_id,
            p.formatted_address,
            p.postcode,
            p.suburb_id,
            p.first_seen_at,
            bs.price       AS latest_price,
            bs.observed_at AS latest_observed_at,
            bs.category    AS latest_category,
            bs.status      AS latest_status
        FROM property p
        LEFT JOIN best_snap bs ON bs.property_id = p.id
        {where_clause}
        ORDER BY {sort_expr}
        LIMIT :limit OFFSET :offset
    """

    rows = (await session.execute(text(sql), params)).mappings().all()
    return [PropertyWithRollup.model_validate(dict(row)) for row in rows]


@router.get("/{property_id}", response_model=PropertyDetail)
async def get_property(
    property_id: int,
    session: AsyncSession = Depends(get_db),
) -> PropertyDetail:
    """Return property + all listing campaigns, each with latest-snapshot summary.

    Listings are ordered by first_seen_at DESC (most-recent campaign first).
    Returns 404 when the property does not exist.
    """
    prop = await session.get(Property, property_id)
    if prop is None:
        raise HTTPException(
            status_code=404, detail=f"property {property_id} not found"
        )

    # Fetch all listings for this property with their latest snapshot in one
    # query using DISTINCT ON.
    sql = text("""
        WITH latest_snap AS (
            SELECT DISTINCT ON (ls.listing_id)
                ls.listing_id,
                ls.price,
                ls.observed_at,
                ls.status
            FROM listing_snapshot ls
            ORDER BY ls.listing_id, ls.observed_at DESC, ls.id DESC
        )
        SELECT
            l.id,
            l.property_id,
            l.suburb_id,
            l.category,
            l.oth_listing_id,
            l.agent_name,
            l.agency_name,
            l.first_seen_at,
            l.last_seen_at,
            l.closed_at,
            l.closure_reason,
            lsn.price       AS snap_price,
            lsn.observed_at AS snap_observed_at,
            lsn.status      AS snap_status
        FROM listing l
        LEFT JOIN latest_snap lsn ON lsn.listing_id = l.id
        WHERE l.property_id = :property_id
        ORDER BY l.first_seen_at DESC
    """)

    rows = (await session.execute(sql, {"property_id": property_id})).mappings().all()

    listings: list[ListingWithSnapshot] = []
    for row in rows:
        d = dict(row)
        snap: SnapshotSummary | None = None
        if d["snap_observed_at"] is not None:
            snap = SnapshotSummary(
                price=d["snap_price"],
                observed_at=d["snap_observed_at"],
                category=d["category"],
                status=d["snap_status"],
            )
        listings.append(
            ListingWithSnapshot(
                id=d["id"],
                property_id=d["property_id"],
                suburb_id=d["suburb_id"],
                category=d["category"],
                oth_listing_id=d["oth_listing_id"],
                agent_name=d["agent_name"],
                agency_name=d["agency_name"],
                first_seen_at=d["first_seen_at"],
                last_seen_at=d["last_seen_at"],
                closed_at=d["closed_at"],
                closure_reason=d["closure_reason"],
                latest_snapshot=snap,
            )
        )

    return PropertyDetail(
        property=PropertyRead.model_validate(prop),
        listings=listings,
    )
