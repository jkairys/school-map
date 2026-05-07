"""`ScrapeSession` — owns the camoufox lifecycle + httpx reuse + rotation.

Bootstrap (lazy on first `http()`): launch camoufox headless, navigate
the OTH home page, perform light human-like interaction, capture cookies
and selected fingerprint headers (User-Agent, Accept-Language). Wrap an
`httpx.AsyncClient` in a custom transport that:

- gates every request through `RateLimiter.acquire(host)`
- overwrites the cookie / UA / Accept-Language headers from the captured
  fingerprint (so rotations apply even on the in-flight request)
- raises `AntiBotError` on 403/429 or sentinel-string match in the body

Auto-rotation is checked at the start of every request: when the request
counter has reached `max_requests` or the bootstrap age has reached
`max_age_seconds`, the session tears down camoufox + httpx and rebootstraps
before sending. Callers may also force a rotation explicitly via
`await session.rotate()`.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from oth_scraper.config import settings
from oth_scraper.rate_limiter import RateLimiter
from oth_scraper.scrape_session.exceptions import AntiBotError

logger = logging.getLogger(__name__)

OTH_ORIGIN = "https://www.onthehouse.com.au"
OTH_HOST = "onthehouse.com.au"

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


@dataclass(frozen=True)
class BootstrapResult:
    """Cookies + headers captured from a single browser bootstrap."""

    cookies: dict[str, str]
    user_agent: str
    accept_language: str


BootstrapFn = Callable[[], Awaitable[BootstrapResult]]


class ScrapeSession:
    """Async context manager that owns a stealth browser bootstrap and an
    httpx client wired through that bootstrap's cookies + fingerprint.

    The bootstrap is lazy — nothing happens until the first `await
    session.http()`. This keeps `__aenter__` cheap so callers can build a
    session in tests without booting camoufox.
    """

    def __init__(
        self,
        *,
        rate_limiter: RateLimiter | None = None,
        max_requests: int | None = None,
        max_age_seconds: int | None = None,
        host: str = OTH_HOST,
        bootstrap_fn: BootstrapFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 30.0,
        inner_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._rate_limiter = rate_limiter or RateLimiter()
        self._max_requests = (
            settings.session_max_requests if max_requests is None else max_requests
        )
        self._max_age_seconds = (
            settings.session_max_age_seconds
            if max_age_seconds is None
            else max_age_seconds
        )
        self._host = host
        self._bootstrap_fn = bootstrap_fn or _default_camoufox_bootstrap
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
                "origin": OTH_ORIGIN,
                "referer": f"{OTH_ORIGIN}/",
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
    from oth_scraper.scrape_session.bootstrap import bootstrap_via_camoufox

    return await bootstrap_via_camoufox()
