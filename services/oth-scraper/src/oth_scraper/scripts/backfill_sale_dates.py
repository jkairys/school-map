"""Backfill listing.sale_date for recentlysold listings created before slice 02.

When slice 02 deployed, ``listing.sale_date`` was added and the reconciler
was updated to populate it on first INSERT.  Listings that already existed
at that point have ``sale_date = NULL`` permanently — their first
``listing_snapshot.raw_payload`` contains the data, but no code ever runs
to set the column.

This script fixes that by:
1. Selecting all ``recentlysold`` Listing rows where ``sale_date IS NULL``.
2. For each, loading the first ``ListingSnapshot`` (by ``observed_at ASC``,
   ``id ASC`` as a tiebreak).
3. Calling ``extract_sale_date(snapshot.raw_payload)``.
4. Running ``UPDATE listing SET sale_date = :date WHERE id = :id`` when a
   date is found.

The script commits in batches of 100 rows so a large run does not hold a
single long transaction open. It is **idempotent**: running again is a no-op
because the ``WHERE sale_date IS NULL`` clause skips already-populated rows.

Usage
-----

    OTH_DATABASE_URL='postgresql+asyncpg://oth:oth@localhost:5433/oth' \\
        uv run python -m oth_scraper.scripts.backfill_sale_dates
"""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from oth_scraper.config import settings
from oth_scraper.db.models import Listing, ListingSnapshot

logger = logging.getLogger(__name__)

# How many listings to process per commit batch.
_BATCH_SIZE = 100


@dataclass
class BackfillCounts:
    """Running totals gathered during backfill."""

    scanned: int = 0
    populated: int = 0
    no_payload: int = 0  # snapshot row is unexpectedly absent
    no_date_in_payload: int = 0  # extractor returned None

    @property
    def processed(self) -> int:
        return self.populated + self.no_payload + self.no_date_in_payload


def _process_row(
    listing_id: int,
    snapshot: ListingSnapshot | None,
    counts: BackfillCounts,
) -> object | None:
    """Return the sale date for one listing, or None.

    Updates *counts* in-place as a side-effect.  Pure (no I/O).
    """
    from oth_scraper.sale_date_extractor import extract_sale_date

    counts.scanned += 1

    if snapshot is None:
        counts.no_payload += 1
        logger.warning("listing id=%d has no snapshot — skipping", listing_id)
        return None

    sale_date = extract_sale_date(snapshot.raw_payload)
    if sale_date is None:
        counts.no_date_in_payload += 1
        logger.debug("listing id=%d: no sale date in payload", listing_id)
        return None

    counts.populated += 1
    return sale_date


async def backfill_sale_dates(
    session_factory: async_sessionmaker[AsyncSession],
) -> BackfillCounts:
    """Core backfill logic — callable from tests and ``__main__``.

    Loads all ``recentlysold`` listings where ``sale_date IS NULL``,
    resolves their earliest snapshot, extracts the date, and commits in
    batches of ``_BATCH_SIZE``.

    Args:
        session_factory: Async session factory bound to the target engine.

    Returns:
        Final ``BackfillCounts`` after processing every eligible listing.
    """
    counts = BackfillCounts()

    # --- load all eligible listing IDs (read-only, no lock needed) ----------
    async with session_factory() as session:
        listing_ids: list[int] = list(
            await session.scalars(
                select(Listing.id)
                .where(
                    Listing.category == "recentlysold",
                    Listing.sale_date.is_(None),
                )
                .order_by(Listing.id)
            )
        )

    total = len(listing_ids)
    logger.info("backfill_sale_dates: %d recentlysold listings with sale_date=NULL", total)

    if total == 0:
        logger.info("backfill_sale_dates: nothing to do")
        return counts

    # --- process in batches --------------------------------------------------
    for batch_start in range(0, total, _BATCH_SIZE):
        batch_ids = listing_ids[batch_start : batch_start + _BATCH_SIZE]

        async with session_factory() as session:
            async with session.begin():
                for listing_id in batch_ids:
                    # Fetch first snapshot (observed_at ASC, id ASC tiebreak)
                    snapshot = await session.scalar(
                        select(ListingSnapshot)
                        .where(ListingSnapshot.listing_id == listing_id)
                        .order_by(
                            ListingSnapshot.observed_at.asc(),
                            ListingSnapshot.id.asc(),
                        )
                        .limit(1)
                    )

                    sale_date = _process_row(listing_id, snapshot, counts)

                    if sale_date is not None:
                        await session.execute(
                            update(Listing)
                            .where(Listing.id == listing_id)
                            .values(sale_date=sale_date)
                        )

        # Progress log every batch (every _BATCH_SIZE rows)
        logger.info(
            "backfill_sale_dates: progress scanned=%d/%d populated=%d "
            "no_payload=%d no_date_in_payload=%d",
            counts.scanned,
            total,
            counts.populated,
            counts.no_payload,
            counts.no_date_in_payload,
        )

    return counts


async def _run() -> None:
    """Entry-point: build the engine from config and run the backfill."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )

    try:
        counts = await backfill_sale_dates(session_factory)
    finally:
        await engine.dispose()

    logger.info(
        "backfill_sale_dates: DONE scanned=%d populated=%d "
        "no_payload=%d no_date_in_payload=%d",
        counts.scanned,
        counts.populated,
        counts.no_payload,
        counts.no_date_in_payload,
    )

    # Surface summary to stdout as well for easy capture in CI/shell.
    print(
        f"backfill complete: scanned={counts.scanned} "
        f"populated={counts.populated} "
        f"no_payload={counts.no_payload} "
        f"no_date_in_payload={counts.no_date_in_payload}"
    )


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
