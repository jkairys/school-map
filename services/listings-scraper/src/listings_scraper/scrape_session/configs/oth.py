"""OTH (onthehouse.com.au) scrape session configuration.

Extracts the OTH-specific constants and anti-bot detection logic that
previously lived directly in `scrape_session/session.py`. Now wrapped in
a `BootstrapConfig` and `AntiBotDetector` so the session can be
re-parameterised for Domain in PR 3.
"""

from listings_scraper.scrape_session.exceptions import AntiBotError
from listings_scraper.scrape_session.session import (
    BootstrapConfig,
    BootstrapResult,
)

import httpx

OTH_ORIGIN = "https://www.onthehouse.com.au"
OTH_HOST = "onthehouse.com.au"
OTH_BOOTSTRAP_URL = f"{OTH_ORIGIN}/"

# Sentinel substrings that show up in the body of an anti-bot challenge
# page (Cloudflare or Imperva/Incapsula). Sourced from school-scraper
# (`scraper.js` → "Checking your browser") plus the canonical Cloudflare /
# Imperva markers; tune via the `oth dev session-smoke` runs.
_SENTINEL_STRINGS: tuple[str, ...] = (
    "Checking your browser",
    "cf-browser-verification",
    "cf_chl_opt",
    "Just a moment",
    "Attention Required! | Cloudflare",
    "_Incapsula_Resource",
    "Request unsuccessful. Incapsula",
)


class _OTHAntiBotDetector:
    """OTH anti-bot detector: checks 403/429 status codes and sentinel strings."""

    def check_response(self, response: httpx.Response) -> None:
        """Raise AntiBotError on 403/429 or sentinel string in body."""
        if response.status_code in (403, 429):
            raise AntiBotError(
                f"OTH responded {response.status_code}; treating as anti-bot block",
                status_code=response.status_code,
            )
        # Body inspection — the transport has already read the body, so
        # `response.text` is cheap and won't consume a stream.
        try:
            body = response.text
        except Exception:
            return
        for sentinel in _SENTINEL_STRINGS:
            if sentinel in body:
                raise AntiBotError(
                    f"Anti-bot sentinel detected in response body: {sentinel!r}",
                    status_code=response.status_code,
                    sentinel=sentinel,
                )

    def check_page(self, body_text: str, cookies: dict[str, str]) -> None:
        """Check a browser-rendered page for anti-bot sentinels."""
        for sentinel in _SENTINEL_STRINGS:
            if sentinel in body_text:
                raise AntiBotError(
                    f"Anti-bot sentinel detected in browser page: {sentinel!r}",
                    sentinel=sentinel,
                )


async def _oth_async_bootstrap() -> BootstrapResult:
    """Default OTH camoufox bootstrap — imported lazily to avoid camoufox cost in tests."""
    from listings_scraper.scrape_session.bootstrap import bootstrap_via_camoufox
    return await bootstrap_via_camoufox()


OTH_CONFIG = BootstrapConfig(
    origin=OTH_ORIGIN,
    host=OTH_HOST,
    bootstrap_url=OTH_BOOTSTRAP_URL,
    bootstrap_fn=_oth_async_bootstrap,
    anti_bot_detector=_OTHAntiBotDetector(),
    max_requests=50,   # matches OTH_SESSION_MAX_REQUESTS env var default
    max_age_seconds=1800,  # matches OTH_SESSION_MAX_AGE_SECONDS env var default
)
"""Pre-built OTH BootstrapConfig. Pass to ScrapeSession(bootstrap_config=OTH_CONFIG)."""
