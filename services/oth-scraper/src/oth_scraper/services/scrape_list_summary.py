"""Service: ScrapeListSummaryService.summary(list_id) → ScrapeListSummary.

All counts are computed within a single transaction so numbers are mutually
consistent (no read-skew between suburb_count, properties_observed, and the
active-listing splits).

The DTO is independent of the ``scrape_list.ScrapeListSummary`` (list-view
model) defined in scrape_list.py — this one carries the rich aggregate data
the Areas dashboard and Area detail page need in one round trip.
"""
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from oth_scraper.db.models.listing import Listing
from oth_scraper.db.models.property import Property
from oth_scraper.db.models.scrape_job import ScrapeJob
from oth_scraper.db.models.scrape_list import ScrapeList, ScrapeListSuburb
from oth_scraper.db.models.scrape_run import ScrapeRun
from oth_scraper.services.scrape_list import ScrapeListFilters, ScrapeListNotFoundError


# --------------------------------------------------------------------------- #
# DTOs                                                                        #
# --------------------------------------------------------------------------- #


class LatestRunCounts(BaseModel):
    queued: int
    running: int
    succeeded: int
    failed: int
    deadletter: int


class LatestRunSummary(BaseModel):
    id: int
    triggered_at: datetime
    completed_at: datetime | None
    status: str  # running | succeeded | partial | failed
    trigger_source: str
    counts: LatestRunCounts


class ActiveListingsByCategory(BaseModel):
    forsale: int
    forrent: int
    recentlysold: int


class AreaSummary(BaseModel):
    """Full summary DTO for a scrape_list / area."""

    id: int
    name: str
    description: str | None
    filters: dict  # the ScrapeListFilters dump
    suburb_count: int
    properties_observed: int
    active_listings: ActiveListingsByCategory
    latest_run: LatestRunSummary | None
    in_flight: bool


# --------------------------------------------------------------------------- #
# Service                                                                      #
# --------------------------------------------------------------------------- #


class ScrapeListSummaryService:
    """Read-only: assembles the area summary DTO in a single transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def summary(self, list_id: int) -> AreaSummary:
        """Return the full area summary or raise ScrapeListNotFoundError."""
        session = self._session

        # All queries run inside the same connection / snapshot.
        # AsyncSession does not expose an explicit BEGIN for reads, but
        # SQLAlchemy 2.0 async sessions operate in autobegin mode: the first
        # statement implicitly opens a transaction that is held until commit
        # or rollback. That is sufficient for consistent reads on Postgres with
        # the default READ COMMITTED isolation (each statement sees the same
        # committed snapshot within one transaction).

        # 1. Fetch the scrape_list row ----------------------------------------
        row = await session.get(ScrapeList, list_id)
        if row is None:
            raise ScrapeListNotFoundError(f"scrape_list {list_id} not found")

        # 2. suburb_count -------------------------------------------------------
        suburb_count_stmt = select(func.count()).where(
            ScrapeListSuburb.scrape_list_id == list_id
        )
        suburb_count: int = (await session.execute(suburb_count_stmt)).scalar_one()

        # Collect suburb ids for the rest of the queries.
        suburb_ids_stmt = select(ScrapeListSuburb.suburb_id).where(
            ScrapeListSuburb.scrape_list_id == list_id
        )
        suburb_ids = list((await session.execute(suburb_ids_stmt)).scalars().all())

        # 3. properties_observed ------------------------------------------------
        # COUNT(DISTINCT property.id) whose suburb_id is in this list's suburbs.
        if suburb_ids:
            props_stmt = select(func.count(distinct(Property.id))).where(
                Property.suburb_id.in_(suburb_ids)
            )
            properties_observed: int = (await session.execute(props_stmt)).scalar_one()
        else:
            properties_observed = 0

        # 4. active_listings by category ----------------------------------------
        if suburb_ids:
            active_stmt = (
                select(
                    Listing.category,
                    func.count(Listing.id).label("cnt"),
                )
                .where(
                    Listing.suburb_id.in_(suburb_ids),
                    Listing.closed_at.is_(None),
                )
                .group_by(Listing.category)
            )
            active_rows = (await session.execute(active_stmt)).all()
        else:
            active_rows = []

        cat_counts: dict[str, int] = {"forsale": 0, "forrent": 0, "recentlysold": 0}
        for cat, cnt in active_rows:
            if cat in cat_counts:
                cat_counts[cat] = cnt
        active_listings = ActiveListingsByCategory(**cat_counts)

        # 5. latest_run ---------------------------------------------------------
        latest_run: LatestRunSummary | None = None

        latest_run_stmt = (
            select(ScrapeRun)
            .where(ScrapeRun.scrape_list_id == list_id)
            .order_by(ScrapeRun.triggered_at.desc())
            .limit(1)
        )
        run_row = (await session.execute(latest_run_stmt)).scalars().first()

        if run_row is not None:
            # Counts from scrape_job grouped by status for this run.
            job_counts_stmt = (
                select(
                    func.count(case((ScrapeJob.status == "queued", 1))).label("queued"),
                    func.count(case((ScrapeJob.status == "running", 1))).label("running"),
                    func.count(case((ScrapeJob.status == "succeeded", 1))).label("succeeded"),
                    func.count(case((ScrapeJob.status == "failed", 1))).label("failed"),
                    func.count(case((ScrapeJob.status == "deadletter", 1))).label(
                        "deadletter"
                    ),
                ).where(ScrapeJob.run_id == run_row.id)
            )
            counts_row = (await session.execute(job_counts_stmt)).one()

            latest_run = LatestRunSummary(
                id=run_row.id,
                triggered_at=run_row.triggered_at,
                completed_at=run_row.completed_at,
                status=run_row.status,
                trigger_source=run_row.trigger_source,
                counts=LatestRunCounts(
                    queued=counts_row.queued,
                    running=counts_row.running,
                    succeeded=counts_row.succeeded,
                    failed=counts_row.failed,
                    deadletter=counts_row.deadletter,
                ),
            )

        in_flight = latest_run is not None and latest_run.status == "running"

        # Build the filters dict from JSONB, validated through ScrapeListFilters.
        filters_dict: dict = ScrapeListFilters.model_validate(
            row.filters or {}
        ).model_dump()

        return AreaSummary(
            id=row.id,
            name=row.name,
            description=row.description,
            filters=filters_dict,
            suburb_count=suburb_count,
            properties_observed=properties_observed,
            active_listings=active_listings,
            latest_run=latest_run,
            in_flight=in_flight,
        )
