"""SuburbSummaryService — all data needed for the suburb detail page in one round trip.

Design notes
------------
- Pure read coordination: no writes, no side effects.
- Executes the minimum number of SQL statements to answer each section.
  Medians use PostgreSQL ``percentile_cont`` and ``DISTINCT ON`` so no rows
  are pulled into Python.
- Definitions come from the OTH admin PRD § Implementation Decisions and the
  slice-04 acceptance criteria.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class RunRef(BaseModel):
    id: int
    completed_at: datetime | None = None


class InFlightRunRef(BaseModel):
    id: int
    triggered_at: datetime


class CategoryDelta(BaseModel):
    new: int
    changed: int


class Deltas(BaseModel):
    forsale: CategoryDelta
    forrent: CategoryDelta
    recentlysold: CategoryDelta


class Totals(BaseModel):
    forsale: int
    forrent: int
    recentlysold: int


class Median(BaseModel):
    value: int | None = None
    n: int


class Medians(BaseModel):
    sold_30d: Median
    asking: Median
    rent: Median


class SuburbSummary(BaseModel):
    id: int
    name: str
    postcode: str
    state: str
    last_completed_run: RunRef | None = None
    in_flight_run: InFlightRunRef | None = None
    deltas: Deltas
    totals: Totals
    medians: Medians


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_ZERO_DELTA = CategoryDelta(new=0, changed=0)
_ZERO_MEDIAN = Median(value=None, n=0)

# Terminal statuses for scrape_job
_TERMINAL = ("succeeded", "failed", "deadletter")
# In-flight statuses for scrape_job
_IN_FLIGHT = ("queued", "running")


class SuburbSummaryService:
    """Compute a full SuburbSummary for one suburb in a small number of SQL queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def summary(self, suburb_id: int) -> SuburbSummary | None:
        """Return the SuburbSummary DTO or None when the suburb does not exist."""
        # 1. Suburb row — also the existence check.
        suburb_row = await self._db.execute(
            text("SELECT id, name, postcode, state FROM suburb WHERE id = :id"),
            {"id": suburb_id},
        )
        suburb = suburb_row.mappings().one_or_none()
        if suburb is None:
            return None

        # 2. Last completed run: the most recent scrape_run for which ALL
        #    scrape_jobs for this suburb are terminal (succeeded / failed /
        #    deadletter).  We also need MAX(completed_at) of those jobs to
        #    populate RunRef.completed_at and to define the delta window.
        last_completed = await self._fetch_last_completed_run(suburb_id)

        # 3. In-flight run: any scrape_run that has at least one job for this
        #    suburb that is queued or running.
        in_flight = await self._fetch_in_flight_run(suburb_id)

        # 4. Deltas — require a completed run to have a meaningful window.
        deltas = await self._fetch_deltas(suburb_id, last_completed)

        # 5. Totals — COUNT(*) FROM listing per category, all-time.
        totals = await self._fetch_totals(suburb_id)

        # 6. Medians.
        medians = await self._fetch_medians(suburb_id)

        return SuburbSummary(
            id=suburb["id"],
            name=suburb["name"],
            postcode=suburb["postcode"],
            state=suburb["state"],
            last_completed_run=last_completed,
            in_flight_run=in_flight,
            deltas=deltas,
            totals=totals,
            medians=medians,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_last_completed_run(
        self, suburb_id: int
    ) -> RunRef | None:
        """Find the most recent run where all jobs for this suburb are terminal.

        Strategy: for each scrape_run that has at least one job for this
        suburb, check whether any job is NOT terminal.  We pick the most
        recent run_id for which no non-terminal job exists.

        Returns a RunRef whose completed_at is the MAX of that run's jobs'
        completed_at for this suburb.
        """
        row = await self._db.execute(
            text("""
                SELECT
                    sr.id                              AS run_id,
                    sr.triggered_at                    AS triggered_at,
                    MAX(sj.completed_at)               AS window_end
                FROM scrape_run sr
                JOIN scrape_job sj
                    ON sj.run_id = sr.id
                   AND sj.suburb_id = :suburb_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM scrape_job sj2
                    WHERE sj2.run_id = sr.id
                      AND sj2.suburb_id = :suburb_id
                      AND sj2.status NOT IN ('succeeded', 'failed', 'deadletter')
                )
                GROUP BY sr.id, sr.triggered_at
                ORDER BY sr.id DESC
                LIMIT 1
            """),
            {"suburb_id": suburb_id},
        )
        result = row.mappings().one_or_none()
        if result is None:
            return None
        return RunRef(
            id=result["run_id"],
            completed_at=result["window_end"],
        )

    async def _fetch_in_flight_run(
        self, suburb_id: int
    ) -> InFlightRunRef | None:
        """Find the most recent run with at least one queued/running job for this suburb."""
        row = await self._db.execute(
            text("""
                SELECT sr.id, sr.triggered_at
                FROM scrape_run sr
                WHERE EXISTS (
                    SELECT 1
                    FROM scrape_job sj
                    WHERE sj.run_id = sr.id
                      AND sj.suburb_id = :suburb_id
                      AND sj.status IN ('queued', 'running')
                )
                ORDER BY sr.id DESC
                LIMIT 1
            """),
            {"suburb_id": suburb_id},
        )
        result = row.mappings().one_or_none()
        if result is None:
            return None
        return InFlightRunRef(
            id=result["id"],
            triggered_at=result["triggered_at"],
        )

    async def _fetch_deltas(
        self,
        suburb_id: int,
        last_completed_run: RunRef | None,
    ) -> Deltas:
        """Count new vs changed snapshots within the last completed run's window.

        Window: [run.triggered_at, MAX(scrape_job.completed_at for this suburb in that run)]
        new     = changed_fields contains '__initial__'
        changed = changed_fields does NOT contain '__initial__'
        """
        if last_completed_run is None or last_completed_run.completed_at is None:
            return Deltas(
                forsale=_ZERO_DELTA,
                forrent=_ZERO_DELTA,
                recentlysold=_ZERO_DELTA,
            )

        # We need the triggered_at of the last completed run to form the window.
        run_row = await self._db.execute(
            text("SELECT triggered_at FROM scrape_run WHERE id = :run_id"),
            {"run_id": last_completed_run.id},
        )
        run_result = run_row.mappings().one_or_none()
        if run_result is None:
            return Deltas(
                forsale=_ZERO_DELTA,
                forrent=_ZERO_DELTA,
                recentlysold=_ZERO_DELTA,
            )

        window_start = run_result["triggered_at"]
        window_end = last_completed_run.completed_at

        rows = await self._db.execute(
            text("""
                SELECT
                    l.category,
                    COUNT(*) FILTER (WHERE '__initial__' = ANY(ls.changed_fields)) AS new_count,
                    COUNT(*) FILTER (WHERE NOT ('__initial__' = ANY(ls.changed_fields))) AS changed_count
                FROM listing_snapshot ls
                JOIN listing l ON l.id = ls.listing_id
                WHERE l.suburb_id = :suburb_id
                  AND ls.observed_at >= :window_start
                  AND ls.observed_at <= :window_end
                GROUP BY l.category
            """),
            {
                "suburb_id": suburb_id,
                "window_start": window_start,
                "window_end": window_end,
            },
        )

        by_category: dict[str, CategoryDelta] = {}
        for row in rows.mappings():
            by_category[row["category"]] = CategoryDelta(
                new=row["new_count"],
                changed=row["changed_count"],
            )

        return Deltas(
            forsale=by_category.get("forsale", _ZERO_DELTA),
            forrent=by_category.get("forrent", _ZERO_DELTA),
            recentlysold=by_category.get("recentlysold", _ZERO_DELTA),
        )

    async def _fetch_totals(self, suburb_id: int) -> Totals:
        """COUNT(*) FROM listing grouped by category — all listings ever, open + closed."""
        rows = await self._db.execute(
            text("""
                SELECT category, COUNT(*) AS cnt
                FROM listing
                WHERE suburb_id = :suburb_id
                GROUP BY category
            """),
            {"suburb_id": suburb_id},
        )
        by_cat: dict[str, int] = {row["category"]: row["cnt"] for row in rows.mappings()}
        return Totals(
            forsale=by_cat.get("forsale", 0),
            forrent=by_cat.get("forrent", 0),
            recentlysold=by_cat.get("recentlysold", 0),
        )

    async def _fetch_medians(self, suburb_id: int) -> Medians:
        """Compute three medians via PostgreSQL percentile_cont + DISTINCT ON."""
        sold_30d = await self._median_sold_30d(suburb_id)
        asking = await self._median_asking(suburb_id)
        rent = await self._median_rent(suburb_id)
        return Medians(sold_30d=sold_30d, asking=asking, rent=rent)

    async def _median_sold_30d(self, suburb_id: int) -> Median:
        """Median sale price from the FIRST snapshot per recentlysold listing
        where listing.sale_date >= CURRENT_DATE - 30 days.

        Uses DISTINCT ON (listing_id) ORDER BY observed_at ASC to take the first
        (canonical) snapshot per listing, then feeds the prices into percentile_cont.
        """
        row = await self._db.execute(
            text("""
                WITH first_snaps AS (
                    SELECT DISTINCT ON (ls.listing_id)
                        ls.price
                    FROM listing_snapshot ls
                    JOIN listing l ON l.id = ls.listing_id
                    WHERE l.suburb_id = :suburb_id
                      AND l.category = 'recentlysold'
                      AND l.sale_date >= CURRENT_DATE - INTERVAL '30 days'
                      AND ls.price IS NOT NULL
                    ORDER BY ls.listing_id, ls.observed_at ASC
                )
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_val,
                    COUNT(*) AS n
                FROM first_snaps
            """),
            {"suburb_id": suburb_id},
        )
        result = row.mappings().one()
        n = result["n"] or 0
        if n == 0:
            return _ZERO_MEDIAN
        return Median(value=int(result["median_val"]), n=n)

    async def _median_asking(self, suburb_id: int) -> Median:
        """Median asking price from the LATEST snapshot per active forsale listing.

        Active = closed_at IS NULL.
        Uses DISTINCT ON (listing_id) ORDER BY observed_at DESC for latest snapshot.
        """
        row = await self._db.execute(
            text("""
                WITH latest_snaps AS (
                    SELECT DISTINCT ON (ls.listing_id)
                        ls.price
                    FROM listing_snapshot ls
                    JOIN listing l ON l.id = ls.listing_id
                    WHERE l.suburb_id = :suburb_id
                      AND l.category = 'forsale'
                      AND l.closed_at IS NULL
                      AND ls.price IS NOT NULL
                    ORDER BY ls.listing_id, ls.observed_at DESC
                )
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_val,
                    COUNT(*) AS n
                FROM latest_snaps
            """),
            {"suburb_id": suburb_id},
        )
        result = row.mappings().one()
        n = result["n"] or 0
        if n == 0:
            return _ZERO_MEDIAN
        return Median(value=int(result["median_val"]), n=n)

    async def _median_rent(self, suburb_id: int) -> Median:
        """Median weekly rent from the LATEST snapshot per active forrent listing."""
        row = await self._db.execute(
            text("""
                WITH latest_snaps AS (
                    SELECT DISTINCT ON (ls.listing_id)
                        ls.price
                    FROM listing_snapshot ls
                    JOIN listing l ON l.id = ls.listing_id
                    WHERE l.suburb_id = :suburb_id
                      AND l.category = 'forrent'
                      AND l.closed_at IS NULL
                      AND ls.price IS NOT NULL
                    ORDER BY ls.listing_id, ls.observed_at DESC
                )
                SELECT
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS median_val,
                    COUNT(*) AS n
                FROM latest_snaps
            """),
            {"suburb_id": suburb_id},
        )
        result = row.mappings().one()
        n = result["n"] or 0
        if n == 0:
            return _ZERO_MEDIAN
        return Median(value=int(result["median_val"]), n=n)
