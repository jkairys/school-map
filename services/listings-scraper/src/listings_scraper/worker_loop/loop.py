"""Worker loop implementation."""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from listings_scraper.config import settings
from listings_scraper.db.engine import AsyncSessionLocal
from listings_scraper.db.models import Suburb
from listings_scraper.listing_reconciler import (
    reconcile_batch,
    run_soft_expiry_sweep,
)
from listings_scraper.vendor import Vendor
from listings_scraper.vendor_clients.base import SearchPage
from listings_scraper.vendor_clients.oth import (
    Category,
    ListingFilters,
    OTHApiClient,
    ParseError,
    PropertyType,
)
from listings_scraper.vendor_resolvers.base import ResolvedSuburb
from listings_scraper.queue import ErrorClass, Job, JobQueue
from listings_scraper.rate_limiter import RateLimiter
from listings_scraper.scrape_session import AntiBotError, ScrapeSession

logger = logging.getLogger(__name__)


class _OTHClientLike(Protocol):
    async def search(
        self,
        suburb: ResolvedSuburb,
        category: Category,
        filters: ListingFilters,
        page: int,
        session: "_ScrapeSessionLike",
    ) -> SearchPage: ...


class _ScrapeSessionLike(Protocol):
    async def http(self) -> httpx.AsyncClient: ...

    async def rotate(self) -> None: ...


SoftExpiryFn = Callable[..., Awaitable[int]]


def classify_exception(exc: BaseException) -> ErrorClass | None:
    """Map an exception raised inside `run_job` to a queue ErrorClass.

    Returns None when the exception is unrecognised; the caller re-raises
    those so the worker process crashes rather than silently mishandling
    them.
    """
    if isinstance(exc, AntiBotError):
        return ErrorClass.ANTIBOT
    if isinstance(exc, (ParseError, pydantic.ValidationError)):
        return ErrorClass.PARSE
    if isinstance(exc, httpx.HTTPStatusError):
        sc = exc.response.status_code
        if 500 <= sc < 600:
            return ErrorClass.TRANSIENT
        # 4xx other than 403/429 (which the session catches as AntiBotError)
        # almost always means a malformed request — retrying won't help.
        return ErrorClass.PARSE
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
    ):
        return ErrorClass.TRANSIENT
    return None


def _filters_from_dict(d: dict) -> ListingFilters:
    pts = tuple(PropertyType(t) for t in (d.get("property_types") or ()))
    return ListingFilters(
        beds_min=d.get("beds_min"),
        beds_max=d.get("beds_max"),
        property_types=pts,
        price_min=d.get("price_min"),
        price_max=d.get("price_max"),
    )


async def _load_suburb(
    session_factory: async_sessionmaker[AsyncSession], suburb_id: int
) -> ResolvedSuburb:
    async with session_factory() as session:
        row = await session.scalar(select(Suburb).where(Suburb.id == suburb_id))
    if row is None:
        raise ParseError(f"job references unknown suburb_id={suburb_id}")
    return ResolvedSuburb(
        id=row.id,
        name=row.name,
        postcode=row.postcode,
        state=row.state,
        source=Vendor.OTH,
        slug=row.slug,
        resolved_at=row.resolved_at,
    )


async def run_job(
    job: Job,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    oth_client: _OTHClientLike,
    scrape_session: _ScrapeSessionLike,
    soft_expiry_sweep: SoftExpiryFn = run_soft_expiry_sweep,
) -> None:
    """Execute one job end-to-end: paginate OTH → reconcile → soft-expiry.

    The soft-expiry sweep runs only after the pagination loop has drained
    successfully. If any page raises, the sweep is skipped — a half-scraped
    feed must not close listings that simply weren't reached this run.
    """
    if job.suburb_id is None:
        raise ParseError(f"job {job.id} has no suburb_id")
    suburb = await _load_suburb(session_factory, job.suburb_id)
    category = Category(job.category)
    filters = _filters_from_dict(job.filters or {})

    page_number = 0
    while True:
        page = await oth_client.search(
            suburb, category, filters, page_number, scrape_session
        )
        if page.listings:
            await reconcile_batch(
                job.suburb_id,
                category,
                page.listings,
                page.raw_payloads,
                session_factory=session_factory,
            )
        if not page.has_next:
            break
        page_number += 1

    await soft_expiry_sweep(
        job.suburb_id, category, session_factory=session_factory
    )


async def worker_task(
    *,
    queue: JobQueue,
    session_factory: async_sessionmaker[AsyncSession],
    oth_client: _OTHClientLike,
    scrape_session: _ScrapeSessionLike,
    shutdown_event: asyncio.Event,
    poll_interval_s: float,
    soft_expiry_sweep: SoftExpiryFn = run_soft_expiry_sweep,
    task_name: str = "worker",
) -> None:
    """One async task's lifetime: claim → run → success/fail until shutdown.

    The task stops claiming new jobs once `shutdown_event` is set, but a
    job already in-flight is allowed to finish (the runner imposes the
    hard deadline at the asyncio.gather level).
    """
    logger.info("%s started", task_name)
    while not shutdown_event.is_set():
        try:
            job = await queue.claim_next()
        except Exception:
            logger.exception("%s: claim_next failed", task_name)
            # Back off briefly so a persistently broken DB doesn't spin.
            await _sleep_or_shutdown(poll_interval_s, shutdown_event)
            continue

        if job is None:
            await _sleep_or_shutdown(poll_interval_s, shutdown_event)
            continue

        logger.info(
            "%s claimed job=%d suburb_id=%s category=%s attempt=%d",
            task_name,
            job.id,
            job.suburb_id,
            job.category,
            job.attempts,
        )
        try:
            await run_job(
                job,
                session_factory=session_factory,
                oth_client=oth_client,
                scrape_session=scrape_session,
                soft_expiry_sweep=soft_expiry_sweep,
            )
        except AntiBotError as exc:
            logger.warning(
                "%s job=%d anti-bot detected: %s — rotating session",
                task_name,
                job.id,
                exc,
            )
            try:
                await scrape_session.rotate()
            except Exception:
                logger.exception(
                    "%s job=%d session rotate failed", task_name, job.id
                )
            await queue.fail(job.id, ErrorClass.ANTIBOT, str(exc))
            continue
        except Exception as exc:
            error_class = classify_exception(exc)
            if error_class is None:
                logger.exception(
                    "%s job=%d unhandled exception — re-raising",
                    task_name,
                    job.id,
                )
                raise
            logger.warning(
                "%s job=%d failed (%s): %s",
                task_name,
                job.id,
                error_class.value,
                exc,
            )
            await queue.fail(job.id, error_class, str(exc))
            continue
        else:
            await queue.complete(job.id)
            logger.info("%s job=%d succeeded", task_name, job.id)
    logger.info("%s shutting down", task_name)


async def _sleep_or_shutdown(
    seconds: float, shutdown_event: asyncio.Event
) -> None:
    """Sleep up to `seconds`, returning early if shutdown is signalled."""
    if seconds <= 0:
        return
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        return


async def run_worker(
    *,
    queue: JobQueue | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    oth_client: _OTHClientLike | None = None,
    scrape_session: _ScrapeSessionLike | None = None,
    rate_limiter: RateLimiter | None = None,
    concurrency: int | None = None,
    poll_interval_s: float | None = None,
    shutdown_grace_s: float | None = None,
    install_signal_handlers: bool = True,
    shutdown_event: asyncio.Event | None = None,
    soft_expiry_sweep: SoftExpiryFn = run_soft_expiry_sweep,
) -> None:
    """Boot N worker tasks, trap SIGTERM/SIGINT, drain cleanly, return.

    Every dependency is injectable so integration tests can replace the
    `OTHApiClient` / `ScrapeSession` with stubs without spinning up
    camoufox or hitting OTH. In production, defaults wire up the real
    `AsyncSessionLocal`, a fresh `RateLimiter`, and a single shared
    `ScrapeSession`.
    """
    if concurrency is None:
        concurrency = settings.worker_concurrency
    if poll_interval_s is None:
        poll_interval_s = settings.worker_poll_interval_seconds
    if shutdown_grace_s is None:
        shutdown_grace_s = settings.worker_shutdown_grace_seconds

    factory = session_factory or AsyncSessionLocal
    queue = queue or JobQueue(factory)
    rate_limiter = rate_limiter or RateLimiter()

    owns_session = scrape_session is None
    session_cm: ScrapeSession | None = None
    if owns_session:
        session_cm = ScrapeSession(rate_limiter=rate_limiter)
        scrape_session = session_cm
    oth_client = oth_client or OTHApiClient()

    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    if install_signal_handlers:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, shutdown_event.set)
                installed_signals.append(sig)
            except NotImplementedError:
                # Windows / non-main-thread event loops cannot install
                # signal handlers; the caller can still set the event.
                logger.debug("signal handler unavailable for %s", sig.name)

    logger.info(
        "run_worker starting concurrency=%d poll_interval=%.2fs grace=%.1fs",
        concurrency,
        poll_interval_s,
        shutdown_grace_s,
    )

    tasks = [
        asyncio.create_task(
            worker_task(
                queue=queue,
                session_factory=factory,
                oth_client=oth_client,
                scrape_session=scrape_session,
                shutdown_event=shutdown_event,
                poll_interval_s=poll_interval_s,
                soft_expiry_sweep=soft_expiry_sweep,
                task_name=f"worker-{i}",
            ),
            name=f"listings-worker-{i}",
        )
        for i in range(concurrency)
    ]

    try:
        # Wait for shutdown OR for any worker to crash unexpectedly.
        wait_shutdown = asyncio.create_task(
            shutdown_event.wait(), name="listings-worker-shutdown-wait"
        )
        done, _pending = await asyncio.wait(
            [wait_shutdown, *tasks],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not shutdown_event.is_set():
            # A worker task returned/crashed before shutdown was requested.
            shutdown_event.set()
        wait_shutdown.cancel()

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=shutdown_grace_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "shutdown grace exceeded; cancelling %d in-flight workers",
                sum(1 for t in tasks if not t.done()),
            )
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Surface unexpected crashes in tasks (anything classify_exception
        # could not handle).
        for t in tasks:
            if t.cancelled():
                continue
            exc = t.exception()
            if exc is not None:
                raise exc
    finally:
        for sig in installed_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, ValueError):
                pass
        if owns_session and session_cm is not None:
            await session_cm.close()
    logger.info("run_worker exited cleanly")
