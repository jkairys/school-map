"""REST endpoints for scrape-list CRUD."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from oth_scraper.db.engine import get_db, get_session_factory
from oth_scraper.queue import JobQueue
from oth_scraper.services.scrape_list import (
    AmbiguousSuburbError,
    ScrapeListCreate,
    ScrapeListNotFoundError,
    ScrapeListRead,
    ScrapeListRunResult,
    ScrapeListSummary,
    ScrapeListUpdate,
    SuburbAddRequest,
    SuburbAlreadyInListError,
    SuburbNotInListError,
    add_suburb_to_list,
    create_list,
    delete_list,
    get_list,
    list_lists,
    remove_suburb_from_list,
    run_list,
    update_list,
)
from oth_scraper.suburb_resolver import (
    AutocompleteUnavailableError,
    Match,
    NoMatchError,
    ResolvedSuburb,
)

router = APIRouter()


class CandidatesResponse(BaseModel):
    candidates: list[Match]


class RunBody(BaseModel):
    """Optional body for POST /scrape-lists/{id}/run.

    ``trigger_source`` defaults to ``'api'`` so callers that send no body
    still get the right provenance label.

    ``suburb_ids`` and ``categories`` are optional narrowing filters:
    - If ``suburb_ids`` is None/empty, all suburbs in the list are used.
    - If ``categories`` is None/empty, all three categories are used.
    - 422 if suburb_ids contains ids not in the list, or categories contains
      unknown values.
    """

    trigger_source: Literal["api", "cli", "scheduler", "retry"] = "api"
    suburb_ids: list[int] | None = None
    categories: list[Literal["forsale", "forrent", "recentlysold"]] | None = None


@router.post("", response_model=ScrapeListRead, status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    body: ScrapeListCreate,
    session: AsyncSession = Depends(get_db),
) -> ScrapeListRead:
    return await create_list(session, body)


@router.get("", response_model=list[ScrapeListSummary])
async def list_endpoint(
    session: AsyncSession = Depends(get_db),
) -> list[ScrapeListSummary]:
    return await list_lists(session)


@router.get("/{list_id}", response_model=ScrapeListRead)
async def get_endpoint(
    list_id: int, session: AsyncSession = Depends(get_db)
) -> ScrapeListRead:
    try:
        return await get_list(session, list_id)
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{list_id}", response_model=ScrapeListRead)
async def update_endpoint(
    list_id: int,
    body: ScrapeListUpdate,
    session: AsyncSession = Depends(get_db),
) -> ScrapeListRead:
    try:
        return await update_list(session, list_id, body)
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    list_id: int, session: AsyncSession = Depends(get_db)
) -> None:
    try:
        await delete_list(session, list_id)
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{list_id}/suburbs",
    response_model=ResolvedSuburb,
    responses={409: {"model": CandidatesResponse}},
)
async def add_suburb_endpoint(
    list_id: int,
    body: SuburbAddRequest,
    session: AsyncSession = Depends(get_db),
) -> ResolvedSuburb:
    try:
        return await add_suburb_to_list(session, list_id, body)
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except AmbiguousSuburbError as e:
        raise HTTPException(
            status_code=409,
            detail={"candidates": [m.model_dump() for m in e.candidates]},
        ) from e
    except SuburbAlreadyInListError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except NoMatchError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except AutocompleteUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/{list_id}/run", response_model=ScrapeListRunResult)
async def run_endpoint(
    list_id: int,
    body: RunBody = RunBody(),
    session: AsyncSession = Depends(get_db),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ScrapeListRunResult:
    queue = JobQueue(session_factory)
    try:
        return await run_list(
            session,
            list_id,
            queue,
            trigger_source=body.trigger_source,
            suburb_ids=body.suburb_ids or None,
            categories=[c for c in body.categories] if body.categories else None,
        )
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.delete(
    "/{list_id}/suburbs/{suburb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_suburb_endpoint(
    list_id: int,
    suburb_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    try:
        await remove_suburb_from_list(session, list_id, suburb_id)
    except ScrapeListNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SuburbNotInListError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
