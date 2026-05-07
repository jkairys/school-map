"""Camoufox-backed stealth session + httpx wiring with rotation policy.

Public surface:
- `ScrapeSession` — async context manager owning the browser bootstrap and
  the httpx client wired through it.
- `BootstrapResult` — value object returned by a bootstrap function.
- `AntiBotError` — raised on response-level anti-bot signals (403/429 or
  challenge sentinels in the body).

The camoufox-driven default bootstrap lives in `bootstrap.py` and is
imported lazily, so tests that inject a fake `bootstrap_fn` don't pay
the playwright/camoufox import cost.
"""

from oth_scraper.scrape_session.exceptions import AntiBotError
from oth_scraper.scrape_session.session import (
    OTH_HOST,
    OTH_ORIGIN,
    BootstrapResult,
    ScrapeSession,
)

__all__ = [
    "AntiBotError",
    "BootstrapResult",
    "OTH_HOST",
    "OTH_ORIGIN",
    "ScrapeSession",
]
