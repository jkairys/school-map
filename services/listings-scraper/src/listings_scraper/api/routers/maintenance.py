"""Admin-only maintenance endpoints.

Routes here are intended for manual operator use (testing, recovery). They
are mounted under `/maintenance` to keep them visually distinct from the
read/write API a future UI would consume.
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.db.engine import get_session_factory
from listings_scraper.listing_reconciler import run_soft_expiry_sweep
from listings_scraper.oth_client.types import Category

router = APIRouter()


class SoftExpirySweepResponse(BaseModel):
    suburb_id: int
    category: Category
    closed: int


@router.post(
    "/run-soft-expiry",
    response_model=SoftExpirySweepResponse,
    summary="Manually run the soft-expiry sweep for one (suburb, category).",
)
async def run_soft_expiry_endpoint(
    suburb_id: int = Query(..., description="Suburb PK to sweep."),
    category: Category = Query(..., description="Listing category to sweep."),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> SoftExpirySweepResponse:
    closed = await run_soft_expiry_sweep(
        suburb_id, category, session_factory=session_factory
    )
    return SoftExpirySweepResponse(
        suburb_id=suburb_id, category=category, closed=closed
    )
