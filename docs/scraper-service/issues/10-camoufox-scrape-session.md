# 10 — Camoufox scrape session with httpx integration and rotation policy

## What to build

The riskiest module in the system. Owns the lifecycle of a stealth browser bootstrap, captures the cookies/headers needed to talk to OTH's API, and exposes them via a configured `httpx.AsyncClient` for fast subsequent requests.

```
class ScrapeSession:
    async def __aenter__(self) -> "ScrapeSession": ...
    async def http(self) -> httpx.AsyncClient: ...   # ready to use
    async def rotate(self) -> None                    # tear down camoufox + httpx, rebootstrap fresh
    async def __aexit__(...) -> None: ...
```

Internally:

1. On `__aenter__` (or first `http()` call): launch camoufox headless with randomised fingerprint, `page.goto("https://www.onthehouse.com.au/")`, allow any anti-bot challenge to settle, perform light human-like interactions, then read out cookies + selected headers (User-Agent, Accept-Language).
2. Construct an `httpx.AsyncClient` pre-loaded with those cookies/headers.
3. Wrap the client so every request goes through the rate limiter (`RateLimiter.acquire("onthehouse.com.au")`).
4. Track `requests_since_bootstrap` and `bootstrap_age`.
5. Auto-rotation triggers (configurable via env): `requests_since_bootstrap >= N` (default 50) OR `age >= T` (default 15 min). On trigger, `rotate()` is called before the next request.
6. Detect anti-bot signals on response (status 403/429, body containing the Cloudflare/Imperva sentinel strings) and raise `AntiBotError` — caller (worker loop) decides to rotate.

This is **HITL** — we need a human in the loop to confirm the bootstrap actually defeats OTH's anti-bot, tune rotation thresholds based on observed behaviour, and document the verification.

## Acceptance criteria

- [ ] `ScrapeSession` async context manager works as the public interface.
- [ ] On bootstrap, captures non-empty cookies and a realistic User-Agent.
- [ ] All httpx requests through the session are gated by the rate limiter.
- [ ] After N requests (configurable) the next call triggers an automatic rotate.
- [ ] After T seconds (configurable) the next call triggers an automatic rotate.
- [ ] `AntiBotError` is raised on 403/429 or detected challenge text.
- [ ] Manual smoke run: a developer runs `oth dev session-smoke` (a CLI command added in this slice) which bootstraps, makes 5 calls against a real OTH suburb search, prints status. Outcome documented in PR description.
- [ ] Rotation thresholds and the verification result are documented in the PR.

## Blocked by

- 06 — Per-host token-bucket rate limiter

## Type

HITL — needs a developer to verify against live OTH and tune rotation parameters.
