"""Coordination layer for ScrapeList CRUD. Both REST and CLI call this.

The Pydantic schemas defined here are also the on-write validators for the
filter JSONB column on ``scrape_list``: unknown keys, negatives, and inverted
ranges are all rejected with a Pydantic ValidationError that the API layer
turns into a 422.

Adding a suburb to a list goes through ``oth_scraper.suburb_resolver.resolve``
(via ``services.suburb``). Ambiguous names raise ``AmbiguousSuburbError``
which the API layer turns into a 409 with a candidate list.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.models.scrape_list import ScrapeList, ScrapeListSuburb
from oth_scraper.db.models.scrape_run import ScrapeRun
from oth_scraper.db.models.suburb import Suburb
from oth_scraper.queue import JobQueue, NewJob
from oth_scraper.services.suburb import resolve_suburb
from oth_scraper.suburb_resolver import Match, ResolvedSuburb

PRODUCER_CATEGORIES: tuple[str, ...] = ("forsale", "forrent", "recentlysold")
"""Categories the producer fans out for every suburb on a list run."""


class ScrapeListFilters(BaseModel):
    """Filter shape stored on scrape_list.filters JSONB.

    Unknown keys are rejected (extra='forbid'). beds_* and price_* must be
    non-negative when present, and min must not exceed max.
    """

    model_config = ConfigDict(extra="forbid")

    beds_min: int | None = Field(default=None, ge=0)
    beds_max: int | None = Field(default=None, ge=0)
    property_types: list[str] | None = None
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_ranges(self) -> "ScrapeListFilters":
        if (
            self.beds_min is not None
            and self.beds_max is not None
            and self.beds_min > self.beds_max
        ):
            raise ValueError("beds_min must be <= beds_max")
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must be <= price_max")
        return self


class ScrapeListCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    filters: ScrapeListFilters = Field(default_factory=ScrapeListFilters)
    cron_schedule: str | None = None


class ScrapeListUpdate(BaseModel):
    """All fields optional; only provided fields are updated."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    filters: ScrapeListFilters | None = None
    cron_schedule: str | None = None


class SuburbAddRequest(BaseModel):
    """Body for POST /scrape-lists/{id}/suburbs.

    `postcode` and `state` are optional disambiguators forwarded to the
    resolver — when the autocomplete finds multiple candidates the caller
    retries with these populated.
    """

    name: str = Field(..., min_length=1)
    postcode: str | None = None
    state: str | None = None


class SuburbInList(BaseModel):
    id: int
    name: str
    postcode: str
    state: str
    oth_slug: str

    model_config = ConfigDict(from_attributes=True)


class ScrapeListRead(BaseModel):
    id: int
    name: str
    description: str | None
    filters: ScrapeListFilters
    cron_schedule: str | None
    created_at: datetime
    suburbs: list[SuburbInList]


class ScrapeListRunResult(BaseModel):
    """Return shape for `POST /scrape-lists/{id}/run`."""

    list_id: int
    run_id: int
    job_ids: list[int]
    count: int


class ScrapeListSummary(BaseModel):
    """Without suburbs — used in list view."""

    id: int
    name: str
    description: str | None
    filters: ScrapeListFilters
    cron_schedule: str | None
    created_at: datetime
    suburb_count: int


class ScrapeListNotFoundError(LookupError):
    pass


class SuburbNotInListError(LookupError):
    pass


class AmbiguousSuburbError(Exception):
    """Raised when add_suburb receives an ambiguous name.

    Carries the list of candidates so the API layer can return them in the
    409 response body.
    """

    def __init__(self, candidates: list[Match]):
        self.candidates = candidates
        super().__init__(
            f"Ambiguous suburb: {len(candidates)} candidates"
        )


class SuburbAlreadyInListError(Exception):
    pass


async def create_list(
    session: AsyncSession, payload: ScrapeListCreate
) -> ScrapeListRead:
    row = ScrapeList(
        name=payload.name,
        description=payload.description,
        filters=payload.filters.model_dump(exclude_none=False),
        cron_schedule=payload.cron_schedule,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_read(row, suburbs=[])


async def list_lists(session: AsyncSession) -> list[ScrapeListSummary]:
    rows = (await session.execute(select(ScrapeList))).scalars().all()
    summaries: list[ScrapeListSummary] = []
    for row in rows:
        count = (
            await session.execute(
                select(ScrapeListSuburb).where(
                    ScrapeListSuburb.scrape_list_id == row.id
                )
            )
        ).all()
        summaries.append(
            ScrapeListSummary(
                id=row.id,
                name=row.name,
                description=row.description,
                filters=ScrapeListFilters.model_validate(row.filters or {}),
                cron_schedule=row.cron_schedule,
                created_at=row.created_at,
                suburb_count=len(count),
            )
        )
    return summaries


async def get_list(session: AsyncSession, list_id: int) -> ScrapeListRead:
    row = await session.get(ScrapeList, list_id)
    if row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")
    suburbs = await _load_suburbs(session, list_id)
    return _to_read(row, suburbs)


async def update_list(
    session: AsyncSession, list_id: int, payload: ScrapeListUpdate
) -> ScrapeListRead:
    row = await session.get(ScrapeList, list_id)
    if row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"]
    if "description" in data:
        row.description = data["description"]
    if "filters" in data and data["filters"] is not None:
        row.filters = data["filters"]
    if "cron_schedule" in data:
        row.cron_schedule = data["cron_schedule"]
    await session.commit()
    await session.refresh(row)
    suburbs = await _load_suburbs(session, list_id)
    return _to_read(row, suburbs)


async def delete_list(session: AsyncSession, list_id: int) -> None:
    row = await session.get(ScrapeList, list_id)
    if row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")
    # Wipe m2m rows explicitly so the operation works the same on backends
    # that don't honour ON DELETE CASCADE (e.g. SQLite without PRAGMA).
    await session.execute(
        delete(ScrapeListSuburb).where(
            ScrapeListSuburb.scrape_list_id == list_id
        )
    )
    await session.delete(row)
    await session.commit()


async def add_suburb_to_list(
    session: AsyncSession,
    list_id: int,
    request: SuburbAddRequest,
) -> ResolvedSuburb:
    """Resolve a suburb name and attach it to the list.

    Raises:
        ScrapeListNotFoundError: list doesn't exist.
        AmbiguousSuburbError: resolver returned multiple candidates.
        SuburbAlreadyInListError: suburb is already attached.
    """
    list_row = await session.get(ScrapeList, list_id)
    if list_row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")

    result = await resolve_suburb(
        request.name,
        session=session,
        postcode=request.postcode,
        state=request.state,
    )
    if isinstance(result, list):
        raise AmbiguousSuburbError(result)

    link = ScrapeListSuburb(scrape_list_id=list_id, suburb_id=result.id)
    session.add(link)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise SuburbAlreadyInListError(
            f"suburb {result.id} already in list {list_id}"
        ) from e
    return result


async def run_list(
    session: AsyncSession,
    list_id: int,
    queue: JobQueue,
    trigger_source: Literal["api", "cli", "scheduler", "retry"] = "api",
) -> ScrapeListRunResult:
    """Fan out one ScrapeJob per (suburb × category) for the list.

    Creates a ``scrape_run`` row in the same transaction as the job rows so
    the fanout is atomic.  The list's filters are snapshotted into both the
    run and each job so editing the list afterwards doesn't mutate in-flight
    provenance. Returns the created run and job IDs in enqueue order.

    Raises:
        ScrapeListNotFoundError: list doesn't exist.
    """
    row = await session.get(ScrapeList, list_id)
    if row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")

    filters_snapshot: dict[str, Any] = dict(row.filters or {})

    suburb_ids_stmt = (
        select(ScrapeListSuburb.suburb_id)
        .where(ScrapeListSuburb.scrape_list_id == list_id)
        .order_by(ScrapeListSuburb.suburb_id)
    )
    suburb_ids = list(
        (await session.execute(suburb_ids_stmt)).scalars().all()
    )

    # Insert the scrape_run row and commit it so child jobs can reference it
    # via FK.  (queue.enqueue() opens its own session/transaction.)
    run = ScrapeRun(
        scrape_list_id=list_id,
        trigger_source=trigger_source,
        filters_snapshot=filters_snapshot,
        status="running",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    job_ids: list[int] = []
    for suburb_id in suburb_ids:
        for category in PRODUCER_CATEGORIES:
            job = await queue.enqueue(
                NewJob(
                    run_id=run.id,
                    suburb_id=suburb_id,
                    category=category,
                    filters=dict(filters_snapshot),
                    scrape_list_id=list_id,
                )
            )
            job_ids.append(job.id)

    return ScrapeListRunResult(
        list_id=list_id, run_id=run.id, job_ids=job_ids, count=len(job_ids)
    )


async def remove_suburb_from_list(
    session: AsyncSession, list_id: int, suburb_id: int
) -> None:
    list_row = await session.get(ScrapeList, list_id)
    if list_row is None:
        raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")
    result = await session.execute(
        delete(ScrapeListSuburb).where(
            ScrapeListSuburb.scrape_list_id == list_id,
            ScrapeListSuburb.suburb_id == suburb_id,
        )
    )
    if result.rowcount == 0:
        raise SuburbNotInListError(
            f"suburb {suburb_id} is not attached to list {list_id}"
        )
    await session.commit()


async def _load_suburbs(
    session: AsyncSession, list_id: int
) -> list[SuburbInList]:
    stmt = (
        select(Suburb)
        .join(
            ScrapeListSuburb, ScrapeListSuburb.suburb_id == Suburb.id
        )
        .where(ScrapeListSuburb.scrape_list_id == list_id)
        .order_by(Suburb.name)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [SuburbInList.model_validate(r) for r in rows]


def _to_read(row: ScrapeList, suburbs: list[SuburbInList]) -> ScrapeListRead:
    filters_dict: dict[str, Any] = dict(row.filters or {})
    return ScrapeListRead(
        id=row.id,
        name=row.name,
        description=row.description,
        filters=ScrapeListFilters.model_validate(filters_dict),
        cron_schedule=row.cron_schedule,
        created_at=row.created_at,
        suburbs=suburbs,
    )
