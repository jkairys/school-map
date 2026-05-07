"""Developer-only CLI commands: smoke-test the scrape session against
real OTH and surface enough detail to tune rotation thresholds.

These commands hit the live OTH service and are only invoked manually
during the HITL verification step for issue 10. They must never be
imported by the worker, the API, or by tests.
"""

import asyncio
import logging
import time

import httpx
import typer

from oth_scraper.config import settings
from oth_scraper.oth_client.payload import SEARCH_URL, build_search_payload
from oth_scraper.oth_client.types import (
    Category,
    ListingFilters,
    ResolvedSuburb,
)
from oth_scraper.rate_limiter import RateLimiter
from oth_scraper.scrape_session import AntiBotError, ScrapeSession

logger = logging.getLogger(__name__)


# Five requests across the three categories with one paginated re-hit, so
# the smoke run exercises all three category code paths plus a same-host
# repeat that should reuse the captured fingerprint without rotation.
_SMOKE_PLAN: tuple[tuple[Category, int], ...] = (
    (Category.FORSALE, 0),
    (Category.FORSALE, 1),
    (Category.FORRENT, 0),
    (Category.RECENTLYSOLD, 0),
    (Category.RECENTLYSOLD, 1),
)

_PADDINGTON = ResolvedSuburb(name="Paddington", postcode="4064", state="QLD")


async def session_smoke_impl() -> int:
    """Bootstrap a session, fire 5 OTH search requests, print the result line.

    Returns 0 if all 5 requests came back 2xx without anti-bot, otherwise 1.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    typer.echo(
        f"smoke: max_requests={settings.session_max_requests} "
        f"max_age_s={settings.session_max_age_seconds} "
        f"rate_min={settings.rate_limit_min_interval}s "
        f"rate_max={settings.rate_limit_max_interval}s"
    )
    typer.echo(
        f"smoke: target suburb={_PADDINGTON.name} {_PADDINGTON.state} "
        f"{_PADDINGTON.postcode}"
    )

    rate_limiter = RateLimiter()
    bootstrap_t0 = time.monotonic()
    failures = 0
    async with ScrapeSession(rate_limiter=rate_limiter) as session:
        # Force the bootstrap up front so its timing is visible separately
        # from the first request's latency.
        client = await session.http()
        bootstrap_elapsed = time.monotonic() - bootstrap_t0
        typer.echo(f"smoke: bootstrap completed in {bootstrap_elapsed:.2f}s")

        filters = ListingFilters()
        for idx, (category, page) in enumerate(_SMOKE_PLAN, start=1):
            payload = build_search_payload(_PADDINGTON, category, filters, page)
            t0 = time.monotonic()
            try:
                response = await client.post(SEARCH_URL, json=payload)
                elapsed_ms = (time.monotonic() - t0) * 1000
                size = len(response.content)
                typer.echo(
                    f"smoke[{idx}/5] {category.value:12s} page={page} "
                    f"status={response.status_code} size={size:>7d}B "
                    f"sentinel=False elapsed={elapsed_ms:.0f}ms "
                    f"requests={session.requests_since_bootstrap} "
                    f"age={session.bootstrap_age_seconds:.1f}s"
                )
                if response.status_code >= 400:
                    failures += 1
            except AntiBotError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                typer.echo(
                    f"smoke[{idx}/5] {category.value:12s} page={page} "
                    f"status={exc.status_code} sentinel=True ({exc.sentinel!r}) "
                    f"elapsed={elapsed_ms:.0f}ms — {exc}"
                )
                failures += 1
            except httpx.HTTPError as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000
                typer.echo(
                    f"smoke[{idx}/5] {category.value:12s} page={page} "
                    f"ERROR {type(exc).__name__}: {exc} "
                    f"elapsed={elapsed_ms:.0f}ms"
                )
                failures += 1

    typer.echo(
        f"smoke: done — {len(_SMOKE_PLAN) - failures}/{len(_SMOKE_PLAN)} ok, "
        f"{failures} failed"
    )
    return 0 if failures == 0 else 1


def session_smoke() -> None:
    """Typer entrypoint — runs the async impl and exits with its return code."""
    rc = asyncio.run(session_smoke_impl())
    raise typer.Exit(code=rc)
