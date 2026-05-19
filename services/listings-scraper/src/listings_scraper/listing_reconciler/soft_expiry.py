"""Soft-expiry sweep — closes listings unseen in their (suburb, category) feed.

v1 closure is deliberately "soft": no detail-page hit, no definitive reason.
Any open Listing whose `last_seen_at` is older than the configured window is
marked `closed_at=NOW(), closure_reason='unknown'`.

This module is part of the listing_reconciler coordination module's public
surface but is not invoked by `reconcile_batch`. The reconciler operates on a
single page of results and cannot tell whether more pages are still coming;
calling the sweep mid-pagination would falsely close every listing on the
later pages. The worker loop (issue 11) is responsible for driving the sweep
once it observes `has_next == False` on a successful job.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.config import settings
from listings_scraper.db.models import Listing
from listings_scraper.oth_client.types import Category

logger = logging.getLogger(__name__)


async def run_soft_expiry_sweep(
    suburb_id: int,
    category: Category,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    soft_expiry_window: timedelta | None = None,
) -> int:
    """Close listings unseen in `(suburb_id, category)` for longer than the window.

    MUST only be invoked at the END of a SUCCESSFUL job for `(suburb_id,
    category)` — i.e. after every page of the OTH search result has been
    reconciled and `has_next == False`. A failed or aborted job's "missing"
    listings are indistinguishable from anti-bot drops; running the sweep on
    one would falsely close every listing in the suburb. The worker loop
    (issue 11) owns this constraint; this function does not, and cannot,
    enforce it.

    The sweep is idempotent: re-running it after closing a listing has no
    effect because the WHERE clause filters on `closed_at IS NULL`.

    Args:
        suburb_id: PK of the suburb whose feed was just enumerated.
        category: Search category that was just enumerated.
        session_factory: Async session factory bound to the live engine.
        soft_expiry_window: Override the default window. Defaults to
            `settings.soft_expiry_days` days.

    Returns:
        Count of listings closed by this sweep.
    """
    window = (
        soft_expiry_window
        if soft_expiry_window is not None
        else timedelta(days=settings.soft_expiry_days)
    )
    cutoff = datetime.now(timezone.utc) - window

    async with session_factory() as session:
        async with session.begin():
            result = await session.execute(
                update(Listing)
                .where(
                    Listing.suburb_id == suburb_id,
                    Listing.category == category.value,
                    Listing.closed_at.is_(None),
                    Listing.last_seen_at < cutoff,
                )
                .values(
                    closed_at=sa_func.now(),
                    closure_reason="unknown",
                )
            )
            closed = result.rowcount or 0

    logger.info(
        "soft_expiry_sweep suburb=%s category=%s window=%s closed=%d",
        suburb_id,
        category.value,
        window,
        closed,
    )
    return closed
