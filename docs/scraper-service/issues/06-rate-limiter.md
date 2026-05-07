# 06 — Per-host token-bucket rate limiter

## What to build

A small async-aware token-bucket rate limiter scoped per hostname, shared across all worker tasks in a single process. Interface:

```
class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic): ...
    async def acquire(self, host: str) -> None  # blocks until a token is available
    def configure(self, host: str, *, min_interval_s: float, jitter_s: float) -> None
```

Defaults pulled from env: `RATE_LIMIT_MIN_INTERVAL_S=1.5`, `RATE_LIMIT_JITTER_S=1.5` → effective spacing 1.5–3.0s with uniform jitter, matching the existing scraper.

The clock is injectable so tests can drive it deterministically. The limiter must work correctly when many coroutines call `acquire("onthehouse.com.au")` concurrently — they form a fair queue.

Cross-process coordination is **not** required in v1 (we run a single worker process by default). Note as a v2 concern in code comment if relevant.

## Acceptance criteria

- [ ] Unit test: 10 concurrent `acquire` calls complete in expected wall-clock time given a fixed (non-jittered) interval.
- [ ] Jitter test: with jitter > 0, observed intervals fall within `[min, min+jitter]` over many samples.
- [ ] Different hosts have independent buckets — `acquire("a")` does not block `acquire("b")`.
- [ ] Configurable per-host limits override the default.
- [ ] Mockable clock — tests don't actually sleep; they advance the clock.

## Blocked by

- 01 — Bootstrap repo skeleton, docker-compose, Postgres, Alembic
