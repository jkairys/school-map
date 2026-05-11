"""REST endpoints for suburb resolution and autocomplete."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.engine import get_db
from oth_scraper.services.suburb import resolve_suburb
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
