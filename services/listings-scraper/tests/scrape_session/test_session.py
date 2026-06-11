"""Unit tests for `ScrapeSession`.

These never launch a real browser. The session accepts an injectable
`bootstrap_fn` returning a canned `BootstrapResult`, and an injectable
`inner_transport` (httpx.MockTransport) that stands in for the real
HTTP transport — so we can assert on the requests the session emits
and feed it canned responses for anti-bot tests.
"""

import asyncio
import json

import httpx
import pytest

from listings_scraper.rate_limiter import RateLimiter
from listings_scraper.scrape_session import (
    AntiBotError,
    BootstrapResult,
    ScrapeSession,
)


SEARCH_URL = "https://www.onthehouse.com.au/odin/api/composite/search"


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class CountingRateLimiter:
    """Stand-in rate limiter that records each acquire and never sleeps."""

    def __init__(self) -> None:
        self.acquired: list[str] = []

    async def acquire(self, host: str) -> None:
        self.acquired.append(host)


def _make_bootstrap_fn(
    *,
    cookies: dict[str, str] | None = None,
    user_agent: str = "TestUA/1.0",
    accept_language: str = "en-AU,en;q=0.9",
    counter: list[int] | None = None,
):
    """Return a bootstrap_fn that yields predictable results and bumps a counter."""
    if counter is None:
        counter = [0]

    async def boot() -> BootstrapResult:
        counter[0] += 1
        i = counter[0]
        return BootstrapResult(
            cookies=dict(cookies or {"session": f"v{i}", "csrf": f"c{i}"}),
            user_agent=f"{user_agent}#{i}",
            accept_language=accept_language,
        )

    boot.counter = counter  # type: ignore[attr-defined]
    return boot


def _ok_handler(body: dict | None = None):
    payload = body if body is not None else {"content": [], "totalElements": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


async def test_bootstrap_is_lazy_and_runs_on_first_http():
    counter = [0]
    boot = _make_bootstrap_fn(counter=counter)
    transport = httpx.MockTransport(_ok_handler())

    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_age_seconds=0,  # disable age-based rotation
    ) as session:
        assert counter[0] == 0
        assert not session.is_bootstrapped
        await session.http()
        assert counter[0] == 1
        assert session.is_bootstrapped


async def test_request_carries_captured_cookies_ua_and_accept_language():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    boot = _make_bootstrap_fn(
        cookies={"sess": "abc", "ot": "xyz"},
        user_agent="TestUA",
    )
    rate = CountingRateLimiter()
    async with ScrapeSession(
        rate_limiter=rate,  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        await client.post(SEARCH_URL, json={"page": 0})

    assert len(captured) == 1
    sent = captured[0]
    cookie_header = sent.headers.get("cookie", "")
    assert "sess=abc" in cookie_header
    assert "ot=xyz" in cookie_header
    assert sent.headers["user-agent"] == "TestUA#1"
    assert sent.headers["accept-language"] == "en-AU,en;q=0.9"
    # Rate-limiter was acquired exactly once for the OTH host.
    assert rate.acquired == ["www.onthehouse.com.au"]


async def test_request_count_triggers_auto_rotation_before_next_request():
    counter = [0]
    boot = _make_bootstrap_fn(counter=counter)
    transport = httpx.MockTransport(_ok_handler())
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_requests=2,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        await client.post(SEARCH_URL, json={"i": 1})
        await client.post(SEARCH_URL, json={"i": 2})
        # Two requests done; the third should trigger a rotate (in the
        # transport pre-send hook) before the request goes out.
        assert counter[0] == 1
        await client.post(SEARCH_URL, json={"i": 3})
        assert counter[0] == 2


async def test_age_triggers_auto_rotation_before_next_request():
    counter = [0]
    boot = _make_bootstrap_fn(counter=counter)
    transport = httpx.MockTransport(_ok_handler())
    clock = FakeClock()
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_age_seconds=10,
        max_requests=0,  # disable count-based rotation
        clock=clock,
    ) as session:
        client = await session.http()
        await client.post(SEARCH_URL, json={"i": 1})
        assert counter[0] == 1
        clock.advance(15)
        await client.post(SEARCH_URL, json={"i": 2})
        assert counter[0] == 2


async def test_explicit_rotate_rebootstraps():
    counter = [0]
    boot = _make_bootstrap_fn(counter=counter)
    transport = httpx.MockTransport(_ok_handler())
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        await session.http()
        assert counter[0] == 1
        await session.rotate()
        assert counter[0] == 2


async def test_rotate_resets_request_counter_and_swaps_cookies():
    counter = [0]
    boot = _make_bootstrap_fn(counter=counter)
    captured_cookies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_cookies.append(request.headers.get("cookie", ""))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=boot,
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        await client.post(SEARCH_URL, json={"i": 1})
        first = session.requests_since_bootstrap
        await session.rotate()
        # rotate() created a new client; old reference is stale.
        client = await session.http()
        await client.post(SEARCH_URL, json={"i": 2})

    assert first == 1
    assert "session=v1" in captured_cookies[0]
    assert "session=v2" in captured_cookies[1]


async def test_403_response_raises_anti_bot_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    transport = httpx.MockTransport(handler)
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        with pytest.raises(AntiBotError) as exc_info:
            await client.post(SEARCH_URL, json={})
    assert exc_info.value.status_code == 403


async def test_429_response_raises_anti_bot_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="too many requests")

    transport = httpx.MockTransport(handler)
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        with pytest.raises(AntiBotError) as exc_info:
            await client.post(SEARCH_URL, json={})
    assert exc_info.value.status_code == 429


async def test_cloudflare_sentinel_in_body_raises_anti_bot_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                "<html><body><h1>Just a moment...</h1>"
                "Checking your browser before accessing"
                "</body></html>"
            ),
        )

    transport = httpx.MockTransport(handler)
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        with pytest.raises(AntiBotError) as exc_info:
            await client.post(SEARCH_URL, json={})
    assert exc_info.value.sentinel is not None
    assert "browser" in exc_info.value.sentinel.lower() or "moment" in exc_info.value.sentinel.lower()


async def test_imperva_sentinel_in_body_raises_anti_bot_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="Request unsuccessful. Incapsula incident ID: 1234",
        )

    transport = httpx.MockTransport(handler)
    async with ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        with pytest.raises(AntiBotError) as exc_info:
            await client.post(SEARCH_URL, json={})
    assert exc_info.value.sentinel is not None
    assert "Incapsula" in exc_info.value.sentinel


async def test_rate_limiter_is_acquired_once_per_request():
    rate = CountingRateLimiter()
    transport = httpx.MockTransport(_ok_handler())
    async with ScrapeSession(
        rate_limiter=rate,  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        for _ in range(3):
            await client.post(SEARCH_URL, json={})
    assert rate.acquired == ["www.onthehouse.com.au"] * 3


async def test_close_is_idempotent_and_blocks_further_use():
    transport = httpx.MockTransport(_ok_handler())
    session = ScrapeSession(
        rate_limiter=CountingRateLimiter(),  # type: ignore[arg-type]
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    )
    await session.http()
    await session.close()
    await session.close()  # idempotent
    with pytest.raises(RuntimeError):
        await session.http()


async def test_real_rate_limiter_serialises_calls():
    """End-to-end check: a tight default-configured RateLimiter actually
    spaces requests apart — the transport really does call acquire()."""
    transport = httpx.MockTransport(_ok_handler())
    limiter = RateLimiter(default_min_interval_s=0.05, default_jitter_s=0.0)
    async with ScrapeSession(
        rate_limiter=limiter,
        bootstrap_fn=_make_bootstrap_fn(),
        inner_transport=transport,
        max_age_seconds=0,
    ) as session:
        client = await session.http()
        loop = asyncio.get_event_loop()
        t0 = loop.time()
        for _ in range(3):
            await client.post(SEARCH_URL, json={})
        elapsed = loop.time() - t0
    # 3 calls @ 50ms apart → at least 100ms total (1st free, 2nd waits 50,
    # 3rd waits 50 more). Allow a generous floor.
    assert elapsed >= 0.09
