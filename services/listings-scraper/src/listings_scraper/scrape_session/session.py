"""`ScrapeSession` — owns the camoufox lifecycle + httpx reuse + rotation.

Bootstrap (lazy on first `http()`): launch camoufox headless, navigate
the vendor home page, perform light human-like interaction, capture cookies
and selected fingerprint headers (User-Agent, Accept-Language). Wrap an
`httpx.AsyncClient` in a custom transport that:

- gates every request through `RateLimiter.acquire(host)`
- overwrites the cookie / UA / Accept-Language headers from the captured
  fingerprint (so rotations apply even on the in-flight request)
- raises `AntiBotError` via the active `AntiBotDetector` on detection signals

Auto-rotation is checked at the start of every request: when the request
counter has reached `max_requests` or the bootstrap age has reached
`max_age_seconds`, the session tears down camoufox + httpx and rebootstraps
before sending. Callers may also force a rotation explicitly via
`await session.rotate()`.

Vendor-specific constants and the default `AntiBotDetector` live in
`scrape_session/configs/oth.py`. `ScrapeSession` is parameterised by a
`BootstrapConfig` dataclass — pass a different config to use the session
with a different vendor.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from listings_scraper.config import settings
from listings_scraper.rate_limiter import RateLimiter
from listings_scraper.scrape_session.exceptions import AntiBotError

logger = logging.getLogger(__name__)

# Legacy constants kept as module-level names for backward-compat.
# The canonical home is scrape_session/configs/oth.py.
OTH_ORIGIN = "https://www.onthehouse.com.au"
OTH_HOST = "onthehouse.com.au"


@dataclass(frozen=True)
class BootstrapResult:
    """Cookies + headers captured from a single browser bootstrap."""

    cookies: dict[str, str]
    user_agent: str
    accept_language: str


BootstrapFn = Callable[[], Awaitable[BootstrapResult]]


class AntiBotDetector(Protocol):
    """Protocol for anti-bot detection strategies.

    Implementations raise `AntiBotError` on detection. OTH uses sentinel
    strings + 403/429 (in `configs/oth.py`). Domain uses Akamai heuristics
    (in `configs/domain.py`, added in PR 3).
    """

    def check_response(self, response: httpx.Response) -> None:
        """Check an HTTP response for anti-bot signals. Raises AntiBotError."""
        ...

    def check_page(self, body_text: str, cookies: dict[str, str]) -> None:
        """Check a browser-rendered page for anti-bot signals. Raises AntiBotError."""
        ...


@dataclass(frozen=True)
class BootstrapConfig:
    """Vendor-specific session bootstrap configuration.

    The OTH config lives in `configs/oth.py`. A Domain config will be added
    in PR 3. Passing a `BootstrapConfig` to `ScrapeSession` lets the same
    session machinery handle multiple vendors without code changes in the core.
    """

    origin: str                    # e.g. "https://www.onthehouse.com.au"
    host: str                      # e.g. "onthehouse.com.au" (for rate-limiter keying)
    bootstrap_url: str             # URL to navigate to warm cookies
    bootstrap_fn: BootstrapFn     # captures cookies + UA + lang; usually camoufox-based
    anti_bot_detector: AntiBotDetector
    max_requests: int              # rotate after this many requests (0 = disable)
    max_age_seconds: int           # rotate after this many seconds (0 = disable)


class ScrapeSession:
    """Async context manager that owns a stealth browser bootstrap and an
    httpx client wired through that bootstrap's cookies + fingerprint.

    The bootstrap is lazy — nothing happens until the first `await
    session.http()`. This keeps `__aenter__` cheap so callers can build a
    session in tests without booting camoufox.

    Vendor-neutral: accepts a `BootstrapConfig` to select OTH or Domain
    bootstrap/detection behaviour. Defaults to the OTH config for backward
    compatibility (matching existing `ScrapeSession()` call sites).
    """

    def __init__(
        self,
        *,
        bootstrap_config: BootstrapConfig | None = None,
        rate_limiter: RateLimiter | None = None,
        max_requests: int | None = None,
        max_age_seconds: int | None = None,
        host: str | None = None,
        bootstrap_fn: BootstrapFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 30.0,
        inner_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # Lazy import to avoid pulling in the oth config at module load time.
        # The default config is OTH for backward-compat.
        if bootstrap_config is None:
            from listings_scraper.scrape_session.configs.oth import OTH_CONFIG
            bootstrap_config = OTH_CONFIG

        self._config = bootstrap_config
        self._rate_limiter = rate_limiter or RateLimiter()
        self._max_requests = (
            settings.session_max_requests
            if max_requests is None
            else max_requests
        )
        self._max_age_seconds = (
            settings.session_max_age_seconds
            if max_age_seconds is None
            else max_age_seconds
        )
        # Individual overrides take precedence over config (existing test seams)
        self._host = host if host is not None else bootstrap_config.host
        self._bootstrap_fn = (
            bootstrap_fn if bootstrap_fn is not None else bootstrap_config.bootstrap_fn
        )
        self._clock = clock
        self._timeout = timeout
        # When supplied, the inner transport is reused across rotations and
        # never closed by the session — owned by the caller (typically a
        # test using httpx.MockTransport).
        self._user_inner_transport = inner_transport

        self._cookies: dict[str, str] = {}
        self._user_agent: str = ""
        self._accept_language: str = ""
        self._client: httpx.AsyncClient | None = None
        self._inner_transport: httpx.AsyncBaseTransport | None = None
        self._owns_inner_transport: bool = False

        # Browser context for Domain page()-based fetching.
        # The browser and context are lazily initialised on first page() call
        # and torn down during close() / rotate(). The httpx bootstrap (http())
        # and the browser bootstrap (page()) are independent lifecycles:
        # - OTH uses http() → bootstrap_fn → httpx client
        # - Domain uses page() → camoufox browser + context
        self._browser: object | None = None          # AsyncCamoufox instance
        self._browser_context: object | None = None  # camoufox BrowserContext

        self._request_count: int = 0
        self._bootstrap_at: float | None = None
        self._lock = asyncio.Lock()
        self._closed: bool = False

    async def __aenter__(self) -> "ScrapeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def http(self) -> httpx.AsyncClient:
        """Return the wrapped httpx client; bootstrap or rotate if needed."""
        if self._closed:
            raise RuntimeError("ScrapeSession is closed")
        async with self._lock:
            if self._client is None:
                await self._bootstrap()
            elif self._should_rotate():
                logger.info(
                    "scrape_session auto-rotate (http()): requests=%d age=%.1fs",
                    self._request_count,
                    self.bootstrap_age_seconds,
                )
                await self._teardown()
                await self._bootstrap()
        assert self._client is not None
        return self._client

    async def page(self) -> object:
        """Return a fresh camoufox Page from the warm browser context.

        Domain clients use this to navigate pages and extract __NEXT_DATA__
        payloads. OTH clients use `http()` instead.

        Architecture note: `page()` maintains a separate camoufox browser
        context from the httpx-based bootstrap that `http()` uses. The browser
        context is lazily initialised on the first `page()` call and reused for
        the lifetime of the session (for Akamai session continuity). Rotation
        (`rotate()` or auto-rotation) tears down both the httpx client AND the
        browser context so a fresh identity is established.

        The returned Page is a new page within the shared context — the caller
        is responsible for closing it after use (typically with a try/finally).
        Each `page()` call increments `_request_count` for rotation accounting.

        Returns:
            A fresh camoufox AsyncPage from the shared BrowserContext.

        Raises:
            RuntimeError: If the session is closed.
        """
        if self._closed:
            raise RuntimeError("ScrapeSession is closed")
        async with self._lock:
            if self._browser_context is None or self._should_rotate_page():
                if self._browser_context is not None:
                    await self._teardown_browser()
                await self._bootstrap_browser()
            self._request_count += 1

        assert self._browser_context is not None
        return await self._browser_context.new_page()

    async def rotate(self) -> None:
        """Tear down the browser + httpx and re-bootstrap fresh."""
        if self._closed:
            raise RuntimeError("ScrapeSession is closed")
        async with self._lock:
            logger.info(
                "scrape_session manual rotate: requests=%d age=%.1fs",
                self._request_count,
                self.bootstrap_age_seconds,
            )
            await self._teardown()
            await self._bootstrap()

    @property
    def requests_since_bootstrap(self) -> int:
        return self._request_count

    @property
    def bootstrap_age_seconds(self) -> float:
        if self._bootstrap_at is None:
            return 0.0
        return max(0.0, self._clock() - self._bootstrap_at)

    @property
    def is_bootstrapped(self) -> bool:
        return self._client is not None

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            await self._teardown()

    # ------------------------------------------------------------------
    # internal — must hold self._lock
    # ------------------------------------------------------------------

    async def _bootstrap(self) -> None:
        result = await self._bootstrap_fn()
        self._cookies = dict(result.cookies)
        self._user_agent = result.user_agent
        self._accept_language = result.accept_language

        if self._user_inner_transport is not None:
            self._inner_transport = self._user_inner_transport
            self._owns_inner_transport = False
        else:
            self._inner_transport = httpx.AsyncHTTPTransport()
            self._owns_inner_transport = True

        transport = _SessionTransport(
            self, self._inner_transport, owns_inner=self._owns_inner_transport
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout,
            headers={
                "accept": "application/json",
                "origin": self._config.origin,
                "referer": f"{self._config.origin}/",
            },
        )
        self._request_count = 0
        self._bootstrap_at = self._clock()
        logger.info(
            "scrape_session bootstrap complete: cookies=%d ua=%r",
            len(self._cookies),
            self._user_agent[:80],
        )

    async def _teardown(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                logger.warning(
                    "scrape_session: error closing httpx client", exc_info=True
                )
        self._client = None
        self._inner_transport = None
        self._owns_inner_transport = False
        self._cookies = {}
        self._user_agent = ""
        self._accept_language = ""
        await self._teardown_browser()

    async def _teardown_browser(self) -> None:
        """Close the camoufox browser context and browser if open."""
        if self._browser_context is not None:
            try:
                await self._browser_context.close()
            except Exception:
                logger.warning(
                    "scrape_session: error closing browser context", exc_info=True
                )
            self._browser_context = None
        if self._browser is not None:
            try:
                await self._browser.__aexit__(None, None, None)
            except Exception:
                logger.warning(
                    "scrape_session: error closing camoufox browser", exc_info=True
                )
            self._browser = None

    async def _bootstrap_browser(self) -> None:
        """Launch a camoufox browser and create a persistent context for page() calls.

        The bootstrap function is called to warm cookies and establish a real
        session (Akamai-friendly). The browser context is kept alive for the
        session lifetime so cookies / session state persist across page() calls.
        This is the Domain equivalent of the httpx bootstrap used by OTH.
        """
        from camoufox import AsyncCamoufox

        # Run the configured bootstrap_fn to warm cookies + capture UA.
        # For Domain this navigates the home page and captures Akamai session cookies.
        result = await self._bootstrap_fn()
        self._cookies = dict(result.cookies)
        self._user_agent = result.user_agent
        self._accept_language = result.accept_language

        # Launch a persistent camoufox browser + context for subsequent page() calls.
        # We launch a NEW browser here (separate from the bootstrap's browser which
        # closes after capturing cookies). This context will carry the captured
        # cookies so Akamai sees a warm session from the start.
        browser_cm = AsyncCamoufox(headless=True, humanize=True)
        self._browser = browser_cm
        await browser_cm.__aenter__()
        self._browser_context = await browser_cm.new_context()

        # Pre-load captured cookies into the browser context so all pages opened
        # from this context automatically carry the bootstrap session identity.
        if self._cookies:
            cookie_list = [
                {"name": k, "value": v, "domain": f".{self._config.host}", "path": "/"}
                for k, v in self._cookies.items()
            ]
            try:
                await self._browser_context.add_cookies(cookie_list)
            except Exception:
                logger.debug(
                    "scrape_session: could not pre-load cookies into browser context",
                    exc_info=True,
                )

        self._request_count = 0
        self._bootstrap_at = self._clock()
        logger.info(
            "scrape_session browser bootstrap complete: cookies=%d ua=%r",
            len(self._cookies),
            self._user_agent[:80],
        )

    def _should_rotate_page(self) -> bool:
        """Check rotation triggers for the browser-based page() path."""
        return self._should_rotate()

    def _should_rotate(self) -> bool:
        if self._max_requests > 0 and self._request_count >= self._max_requests:
            return True
        if (
            self._max_age_seconds > 0
            and self.bootstrap_age_seconds >= self._max_age_seconds
        ):
            return True
        return False

    # ------------------------------------------------------------------
    # internal — called from the transport, must NOT hold self._lock on entry
    # ------------------------------------------------------------------

    async def _on_request(self, request: httpx.Request) -> None:
        async with self._lock:
            if self._closed:
                raise RuntimeError("ScrapeSession is closed")
            if self._client is None:
                # Defensive: a request hit the transport before bootstrap.
                # In practice `http()` always bootstraps first, but guard
                # against an in-flight rotate that closed mid-flight.
                await self._bootstrap()
            elif self._should_rotate():
                logger.info(
                    "scrape_session in-transport rotate: requests=%d age=%.1fs",
                    self._request_count,
                    self.bootstrap_age_seconds,
                )
                await self._teardown()
                await self._bootstrap()

            cookies = self._cookies
            user_agent = self._user_agent
            accept_language = self._accept_language
            self._request_count += 1

        # Apply captured fingerprint to the in-flight request, overriding
        # whatever httpx merged from the (intentionally unused) client jar.
        if cookies:
            request.headers["cookie"] = "; ".join(
                f"{k}={v}" for k, v in cookies.items()
            )
        if user_agent:
            request.headers["user-agent"] = user_agent
        if accept_language:
            request.headers["accept-language"] = accept_language

        host = request.url.host or self._host
        await self._rate_limiter.acquire(host)

    def _check_response(self, response: httpx.Response) -> None:
        self._config.anti_bot_detector.check_response(response)


class _SessionTransport(httpx.AsyncBaseTransport):
    """Custom httpx transport: rotation gate + rate limit + anti-bot detect."""

    def __init__(
        self,
        session: ScrapeSession,
        inner: httpx.AsyncBaseTransport,
        *,
        owns_inner: bool,
    ) -> None:
        self._session = session
        self._inner = inner
        self._owns_inner = owns_inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self._session._on_request(request)
        response = await self._inner.handle_async_request(request)
        # Read the body so sentinel-string detection is possible and so
        # callers can re-read `response.text` without an extra round-trip.
        try:
            await response.aread()
        except Exception:
            logger.debug("scrape_session: response.aread() failed", exc_info=True)
        self._session._check_response(response)
        return response

    async def aclose(self) -> None:
        if self._owns_inner:
            await self._inner.aclose()


async def _default_camoufox_bootstrap() -> BootstrapResult:
    # Imported lazily so unit tests don't pull in camoufox/playwright.
    from listings_scraper.scrape_session.bootstrap import bootstrap_via_camoufox

    return await bootstrap_via_camoufox()
