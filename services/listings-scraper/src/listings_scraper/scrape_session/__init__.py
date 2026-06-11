"""Camoufox-backed stealth session + httpx wiring with rotation policy.

Public surface:
- `ScrapeSession` — async context manager owning the browser bootstrap and
  the httpx client wired through it.
- `BootstrapResult` — value object returned by a bootstrap function.
- `BootstrapConfig` — vendor-specific session configuration dataclass.
- `AntiBotDetector` — Protocol for anti-bot detection strategies.
- `AntiBotError` — raised on response-level anti-bot signals (403/429 or
  challenge sentinels in the body).

The camoufox-driven default bootstrap lives in `bootstrap.py` and is
imported lazily, so tests that inject a fake `bootstrap_fn` don't pay
the playwright/camoufox import cost.

Vendor-specific configs live in `configs/oth.py` (and `configs/domain.py`
in PR 3).
"""

from listings_scraper.scrape_session.exceptions import AntiBotError
from listings_scraper.scrape_session.session import (
    AntiBotDetector,
    BootstrapConfig,
    BootstrapResult,
    OTH_HOST,
    OTH_ORIGIN,
    ScrapeSession,
)

__all__ = [
    "AntiBotDetector",
    "AntiBotError",
    "BootstrapConfig",
    "BootstrapResult",
    "OTH_HOST",
    "OTH_ORIGIN",
    "ScrapeSession",
]
