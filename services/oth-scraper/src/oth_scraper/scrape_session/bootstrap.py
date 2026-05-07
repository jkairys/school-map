"""Camoufox-backed bootstrap for ScrapeSession.

Launches a stealth Firefox via camoufox, navigates the OTH home page,
gives any anti-bot challenge time to settle, performs light human-like
interaction (mouse movement + scroll, mirroring the school-scraper
prior art at services/school-scraper/scraper.js), and extracts cookies +
the User-Agent / Accept-Language headers.

This module is imported lazily by `scrape_session.session` so unit tests
that inject a fake `bootstrap_fn` never have to import camoufox.
"""

import asyncio
import logging
import random

from camoufox import AsyncCamoufox

from oth_scraper.scrape_session.session import OTH_ORIGIN, BootstrapResult

logger = logging.getLogger(__name__)

_NAV_TIMEOUT_MS = 60_000
_ANTI_BOT_WAIT_S = 10.0


async def bootstrap_via_camoufox() -> BootstrapResult:
    """Launch camoufox once, capture cookies + selected fingerprint headers."""
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(
                f"{OTH_ORIGIN}/",
                wait_until="networkidle",
                timeout=_NAV_TIMEOUT_MS,
            )
            await _settle_anti_bot(page)
            await _human_like_interaction(page)
            cookies_raw = await context.cookies()
            user_agent = await page.evaluate("() => navigator.userAgent") or ""
            accept_language = (
                await page.evaluate(
                    "() => navigator.language || (navigator.languages && "
                    "navigator.languages[0]) || ''"
                )
                or "en-AU,en;q=0.9"
            )
        finally:
            await page.close()
            await context.close()

    cookies = {
        c["name"]: c["value"]
        for c in cookies_raw
        if c.get("name") and c.get("value") is not None
    }
    logger.info(
        "camoufox bootstrap captured cookies=%d ua=%r lang=%r",
        len(cookies),
        user_agent[:80],
        accept_language,
    )
    return BootstrapResult(
        cookies=cookies,
        user_agent=user_agent,
        accept_language=accept_language,
    )


async def _settle_anti_bot(page) -> None:
    """If the OTH home page shows a Cloudflare-style wall, wait for it."""
    try:
        body = await page.evaluate(
            "() => (document.body && document.body.innerText) || ''"
        )
    except Exception:
        body = ""
    if "Checking your browser" in body or "Just a moment" in body:
        logger.info(
            "camoufox bootstrap: anti-bot wall detected, waiting %.0fs",
            _ANTI_BOT_WAIT_S,
        )
        await asyncio.sleep(_ANTI_BOT_WAIT_S)


async def _human_like_interaction(page) -> None:
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        width = viewport["width"]
        height = viewport["height"]
        for _ in range(2):
            await page.mouse.move(
                random.randint(0, max(1, width - 1)),
                random.randint(0, max(1, height - 1)),
            )
            await asyncio.sleep(random.uniform(0.2, 0.7))
        await page.evaluate("() => window.scrollBy(0, window.innerHeight / 2)")
        await asyncio.sleep(random.uniform(0.5, 1.5))
    except Exception:
        # Best-effort — not fatal if mouse/scroll calls fail.
        logger.debug("camoufox bootstrap: human-like interaction failed", exc_info=True)
