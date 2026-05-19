# CLAUDE.md — `scrape_session`

Deep module that owns the camoufox lifecycle, captures the cookies +
fingerprint headers OTH's anti-bot challenge expects, exposes them via a
configured `httpx.AsyncClient`, and rotates the whole stack on age /
request-count / 403-or-429.

The module is the riskiest in the service: only the live `oth dev
session-smoke` command can prove it actually defeats OTH's anti-bot.

## Public surface

- `ScrapeSession` — async context manager. Lazy-bootstraps on first
  `await session.http()`. Methods: `http()`, `rotate()`, `close()`.
  Properties: `is_bootstrapped`, `requests_since_bootstrap`,
  `bootstrap_age_seconds`.
- `BootstrapResult(cookies, user_agent, accept_language)` — value object
  returned by a bootstrap function. Injectable for tests.
- `AntiBotError` — raised by the session's transport on 403 / 429 / a
  sentinel string in the body. Carries `status_code` and `sentinel`.

Importing the package never imports `camoufox`. The default bootstrap
lives in `bootstrap.py` and is loaded via lazy import only when the real
bootstrap actually runs. Unit tests inject a fake `bootstrap_fn` and
never touch playwright.

## Lifecycle

```
ScrapeSession(...)            # cheap; nothing happens
  async with session:
    await session.http()      # → triggers bootstrap (camoufox launch)
    await client.post(...)    # → transport applies cookies/UA, rate-limits, runs anti-bot check
    ...
    await session.rotate()    # tear down camoufox + httpx, re-bootstrap fresh
  # __aexit__ → close()       # idempotent
```

Auto-rotation triggers, checked at every `http()` call AND at the start
of every request (in the transport):

- `requests_since_bootstrap >= max_requests` (default 50, env
  `OTH_SESSION_MAX_REQUESTS`)
- `bootstrap_age_seconds >= max_age_seconds` (default 1800, env
  `OTH_SESSION_MAX_AGE_SECONDS`)

Set either to `0` to disable that trigger. The transport-level recheck
exists because callers may keep a long-lived reference to the
`AsyncClient` and never go through `http()` between requests; the
transport guarantees rotation happens before the next request escapes.

## Why the cookie/UA injection lives in the transport, not the client

httpx merges cookies from `client.cookies` into the request headers in
`client.build_request()` — *before* `client.send()` runs. By the time
the request reaches a transport, its `cookie` header is already frozen.

If we put cookies on `client.cookies` and rotated cookies during the
transport's pre-send hook, the in-flight request would still ship the
old cookies. So `ScrapeSession` deliberately does NOT load cookies onto
`client.cookies`; instead the custom transport (`_SessionTransport`)
overwrites the `cookie`, `user-agent`, and `accept-language` headers on
the request object directly, after any rotation has run. This keeps the
"rotate-before-the-very-next-request" semantics correct.

## Rotation locking

A single `asyncio.Lock` (`session._lock`) serializes:

- bootstrap
- teardown
- the rotation-check + counter increment in `_on_request`
- `close()` and `rotate()`

The lock is held across `_bootstrap` and `_teardown`, which can be slow
(camoufox launch). Concurrent requests on the same client serialize at
the lock during the pre-send hook, then release before the actual HTTP
call. Rate limiting happens after the lock release, on a separate
per-host lock owned by `RateLimiter`.

## Anti-bot detection

After every response the transport reads the body (so subsequent
`response.text` is free) and checks:

- status code 403 or 429 → `AntiBotError(status_code=...)`
- body contains any of `_SENTINEL_STRINGS` → `AntiBotError(sentinel=...)`

Sentinel list lives at the top of `session.py`. Initial set sourced from
the JS school-scraper prior art (`Checking your browser`) plus canonical
Cloudflare and Imperva/Incapsula markers. Tune by adding strings
observed during smoke runs — keep substring matches, not regexes,
unless we hit a false-positive.

The transport raises `AntiBotError`. The worker loop (issue 11) catches
it, calls `session.rotate()`, and retries once. The session does NOT
auto-rotate on anti-bot — the caller decides.

## Testability seams

`ScrapeSession.__init__` accepts:

- `bootstrap_fn` — async callable returning `BootstrapResult`. Default
  is the lazy camoufox bootstrap. Tests pass a counter-bumping fake.
- `inner_transport` — an `httpx.AsyncBaseTransport`. When provided, the
  session reuses it across rotations and never closes it (it's owned by
  the caller). Tests pass `httpx.MockTransport(handler)` to feed canned
  responses and capture outbound requests.
- `clock` — monotonic clock callable. Tests pass a `FakeClock` to
  trigger age-based rotation deterministically.
- `rate_limiter` — a `RateLimiter` (or stand-in with `acquire(host)`).
  Tests pass a `CountingRateLimiter` to assert one acquire per request.

`pytest_httpx` does NOT work here, because the fixture replaces the
client's transport at construction — but our session installs its own
`_SessionTransport` and pytest_httpx can't reach the inner one. Use
`httpx.MockTransport` injected via `inner_transport=` instead.

## Camoufox bootstrap details (`bootstrap.py`)

- `AsyncCamoufox(headless=True, humanize=True)` — humanize enables
  camoufox's built-in cursor-movement humanization. We do NOT pin
  `os=`/`fingerprint=` so camoufox randomizes per launch. If smoke runs
  fail, narrow `os=` to a single platform before adding more knobs.
- `page.goto(OTH home, wait_until="networkidle", timeout=60s)`.
- If the rendered body contains `Checking your browser` /
  `Just a moment`, sleep 10s for the challenge to clear. If smoke shows
  the wall persisting, raise the wait or add a polling check.
- Then a light human-like dance: 2 randomized mouse moves with sleeps,
  then a half-viewport scroll. Mirrors the JS school-scraper's
  `humanLikeInteraction`. Best-effort — failures are logged but don't
  abort the bootstrap.
- Capture `context.cookies()` (filtered to name/value pairs),
  `navigator.userAgent`, and `navigator.language` (fallback
  `en-AU,en;q=0.9`). Close the page+context but let `AsyncCamoufox.__aexit__`
  close the browser.

## Smoke command

`oth dev session-smoke` runs `cli/dev_commands.py:session_smoke_impl`.
Hits live OTH with five requests (forsale p0+p1, forrent p0+p1,
recentlysold p0) against Paddington QLD 4064. Prints status, body size,
sentinel flag, elapsed ms, and the session counters per request. Exits
non-zero on any failure.

This is the HITL gate for issue 10: the PR can't open until smoke
output is captured and pasted into the description.

## What this module does NOT do

- Does not know about jobs, listings, or the DB. Pure infra.
- Does not auto-rotate on `AntiBotError` — that's the worker loop's
  job, so the worker can decide whether to retry the in-flight job.
- Does not coordinate across processes. Single-worker only; if v2 ever
  scales out, the rotation/rate-limit state needs a shared store.
- Does not retry on transient HTTP errors (5xx / timeouts) — those bubble
  up as `httpx.HTTPError` for the worker loop to classify.
