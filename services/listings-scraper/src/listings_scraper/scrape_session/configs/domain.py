"""Domain (domain.com.au) scrape session configuration.

Provides:
- `DOMAIN_CONFIG`: BootstrapConfig for Domain sessions
- `_DomainAntiBotDetector`: Akamai-aware anti-bot detector
- `_bootstrap_domain()`: camoufox bootstrap function for Domain

Akamai anti-bot signals checked (sourced from spike observations):
1. HTTP 429 → hard block.
2. HTTP 200 with body size < 5 KB → likely a redirect/challenge page
   rather than a real search result (Domain's search pages are 300-600 KB).
3. Cookie `_abck` containing `~-1~` → Akamai's "bot verdict" cookie.
   When Akamai concludes the session is a bot, it encodes `-1` in the
   `_abck` cookie value. This is the strongest signal.

Implementation note (session architecture):
  Domain requires a browser page for each search request because the listing
  data is embedded in the Next.js SSR HTML, not in a separate XHR endpoint.
  The Domain ScrapeSession uses `session.page()` (returns a fresh camoufox
  Page from a persistent BrowserContext) rather than `session.http()`.
  The bootstrap warms the browser context with real cookies; subsequent
  page() calls reuse the same context for session continuity.
"""

import httpx

from listings_scraper.scrape_session.exceptions import AntiBotError
from listings_scraper.scrape_session.session import (
    BootstrapConfig,
    BootstrapResult,
)

DOMAIN_ORIGIN = "https://www.domain.com.au"
DOMAIN_HOST = "domain.com.au"
DOMAIN_BOOTSTRAP_URL = f"{DOMAIN_ORIGIN}/"

# Body size floor: Domain search pages are 300+ KB when fully rendered.
# A body smaller than this is almost certainly a redirect or challenge page.
_MIN_BODY_SIZE_BYTES = 5_000

# Akamai bot-verdict cookie name and sentinel substring.
# When Akamai concludes the session is a bot, the `_abck` cookie encodes
# "~-1~" in its value. Checking for this substring is the most reliable
# signal available without parsing the full Akamai token.
_AKAMAI_COOKIE_NAME = "_abck"
_AKAMAI_BOT_VERDICT = "~-1~"


class _DomainAntiBotDetector:
    """Akamai-aware anti-bot detector for Domain sessions."""

    def check_response(self, response: httpx.Response) -> None:
        """Check an HTTP response for Domain/Akamai anti-bot signals.

        Raises AntiBotError on:
        - HTTP 429 (rate limited / blocked)
        - HTTP 200 with a suspiciously small body (likely a challenge page)
        - Akamai bot-verdict cookie (`_abck` containing `~-1~`)
        """
        if response.status_code == 429:
            raise AntiBotError(
                f"Domain responded {response.status_code}; treating as Akamai block",
                status_code=response.status_code,
            )
        if response.status_code == 200:
            try:
                body_size = len(response.content)
            except Exception:
                body_size = 0
            if body_size > 0 and body_size < _MIN_BODY_SIZE_BYTES:
                raise AntiBotError(
                    f"Domain returned HTTP 200 but body is suspiciously small "
                    f"({body_size} bytes < {_MIN_BODY_SIZE_BYTES} byte floor) — "
                    "likely an Akamai challenge or redirect page",
                    status_code=200,
                )
        # Check Akamai bot-verdict cookie
        cookies = dict(response.cookies)
        _check_akamai_cookies(cookies)

    def check_page(self, body_text: str, cookies: dict[str, str]) -> None:
        """Check a browser-rendered page for Akamai anti-bot signals.

        The primary signal for browser-based Domain scraping is the `_abck`
        cookie. If Akamai has flagged the session, the cookie will contain
        `~-1~` in its value.
        """
        _check_akamai_cookies(cookies)


def _check_akamai_cookies(cookies: dict[str, str]) -> None:
    """Raise AntiBotError if the Akamai bot-verdict cookie is set."""
    abck = cookies.get(_AKAMAI_COOKIE_NAME, "")
    if _AKAMAI_BOT_VERDICT in abck:
        raise AntiBotError(
            f"Akamai bot-verdict detected: {_AKAMAI_COOKIE_NAME!r} contains "
            f"{_AKAMAI_BOT_VERDICT!r} — session has been flagged as a bot",
            sentinel=f"{_AKAMAI_COOKIE_NAME}:{_AKAMAI_BOT_VERDICT}",
        )


async def _bootstrap_domain() -> BootstrapResult:
    """Camoufox bootstrap for Domain sessions.

    Navigates to the Domain home page, waits for __NEXT_DATA__ to confirm
    the page has rendered (not a challenge page), and captures cookies + UA.

    Uses humanize=True, headless=True per the spike observations — these
    are sufficient to pass Akamai's initial bot detection on the landing page.
    """
    import asyncio
    import logging
    import random

    from camoufox import AsyncCamoufox

    _logger = logging.getLogger(__name__)

    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(
                DOMAIN_BOOTSTRAP_URL,
                wait_until="networkidle",
                timeout=60_000,
            )
            # Wait briefly for __NEXT_DATA__ script tag as a readiness signal.
            # This confirms Domain's Next.js has hydrated rather than serving
            # a challenge page.
            try:
                await page.wait_for_selector(
                    '#__NEXT_DATA__',
                    timeout=15_000,
                )
            except Exception:
                _logger.warning(
                    "domain bootstrap: __NEXT_DATA__ element not found — "
                    "page may not have fully rendered; continuing anyway"
                )

            # Light human-like interaction to strengthen the Akamai session
            try:
                viewport = page.viewport_size
                if viewport:
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
                _logger.debug(
                    "domain bootstrap: human-like interaction failed", exc_info=True
                )

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
    _logger.info(
        "domain bootstrap captured cookies=%d ua=%r lang=%r",
        len(cookies),
        user_agent[:80],
        accept_language,
    )
    return BootstrapResult(
        cookies=cookies,
        user_agent=user_agent,
        accept_language=accept_language,
    )


DOMAIN_CONFIG = BootstrapConfig(
    origin=DOMAIN_ORIGIN,
    host=DOMAIN_HOST,
    bootstrap_url=DOMAIN_BOOTSTRAP_URL,
    bootstrap_fn=_bootstrap_domain,
    anti_bot_detector=_DomainAntiBotDetector(),
    max_requests=50,
    max_age_seconds=1800,
)
"""Pre-built Domain BootstrapConfig. Pass to ScrapeSession(bootstrap_config=DOMAIN_CONFIG)."""
