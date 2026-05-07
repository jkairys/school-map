"""REST endpoints for suburb resolution."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.engine import get_db
from oth_scraper.services.suburb import resolve_suburb
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
