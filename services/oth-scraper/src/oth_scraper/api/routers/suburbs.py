"""REST endpoints for suburb resolution, autocomplete, and summary."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from oth_scraper.db.engine import get_db
from oth_scraper.db.models.suburb import Suburb
from oth_scraper.services.suburb import resolve_suburb
from oth_scraper.services.suburb_summary import SuburbSummary, SuburbSummaryService
from oth_scraper.suburb_autocomplete import autocomplete as _autocomplete
from oth_scraper.suburb_resolver import (
    AutocompleteUnavailableError,
    Match,
    NoMatchError,
    ResolvedSuburb,
)

router = APIRouter()


class ResolveRequest(BaseModel):
    name: str = Field(..., min_length=1)
    postcode: str | None = None
    state: str | None = None


class CandidatesResponse(BaseModel):
    candidates: list[Match]


@router.get("/autocomplete", response_model=list[Match])
async def autocomplete_endpoint(
    q: str = Query(default="", description="Suburb search string. Empty returns []."),
) -> list[Match]:
    """Return OTH autocomplete candidates for a query string.

    Read-only: never persists to the database. Use POST /suburbs/resolve to
    cache a confirmed match.

    - Empty `q` → returns `[]` immediately (no OTH call).
    - OTH errors → 503 Service Unavailable.
    """
    try:
        return await _autocomplete(q)
    except AutocompleteUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post(
    "/resolve",
    response_model=ResolvedSuburb,
    responses={409: {"model": CandidatesResponse}},
)
async def resolve_endpoint(
    body: ResolveRequest,
    session: AsyncSession = Depends(get_db),
) -> ResolvedSuburb:
    try:
        result = await resolve_suburb(
            body.name, session=session, postcode=body.postcode, state=body.state
        )
    except NoMatchError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except AutocompleteUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if isinstance(result, list):
        raise HTTPException(
            status_code=409,
            detail={"candidates": [m.model_dump() for m in result]},
        )
    return result


@router.get("/{suburb_id}", response_model=ResolvedSuburb)
async def get_suburb_endpoint(
    suburb_id: int,
    session: AsyncSession = Depends(get_db),
) -> ResolvedSuburb:
    """Return a single suburb by its database id.

    Returns the same shape as POST /suburbs/resolve so the Run Detail page
    can display ``"<name> <postcode>"`` group headers.

    Returns **404** when the suburb does not exist.
    """
    result = await session.execute(select(Suburb).where(Suburb.id == suburb_id))
    suburb = result.scalar_one_or_none()
    if suburb is None:
        raise HTTPException(status_code=404, detail=f"Suburb {suburb_id} not found")
    return ResolvedSuburb.model_validate(suburb)


@router.get("/{suburb_id}/summary", response_model=SuburbSummary)
async def suburb_summary_endpoint(
    suburb_id: int,
    session: AsyncSession = Depends(get_db),
) -> SuburbSummary:
    """Return the full summary DTO for one suburb.

    Packs everything the suburb detail page needs into a single round trip:
    last completed run, in-flight run (if any), new/changed deltas per
    category, all-time totals, and three price medians.

    Returns **404** when the suburb does not exist.
    """
    svc = SuburbSummaryService(session)
    result = await svc.summary(suburb_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Suburb {suburb_id} not found")
    return result
