import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from oth_scraper.config import settings

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
Rng = Callable[[], float]


@dataclass(frozen=True)
class _BucketConfig:
    min_interval_s: float
    jitter_s: float


def _default_min_interval() -> float:
    return float(settings.rate_limit_min_interval)


def _default_jitter() -> float:
    span = float(settings.rate_limit_max_interval) - float(settings.rate_limit_min_interval)
    return max(0.0, span)


class RateLimiter:
    """Async-aware token-bucket rate limiter scoped per hostname.

    Many concurrent waiters on the same host form a fair FIFO queue (asyncio.Lock
    queues acquirers in arrival order). Different hosts have fully independent
    buckets, so traffic to one host never blocks another.

    The clock and sleep functions are injectable so tests can drive the limiter
    without real wall-clock waits.
    """

    def __init__(
        self,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        rng: Rng = random.random,
        default_min_interval_s: float | None = None,
        default_jitter_s: float | None = None,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._rng = rng
        self._default = _BucketConfig(
            min_interval_s=(
                _default_min_interval() if default_min_interval_s is None else default_min_interval_s
            ),
            jitter_s=_default_jitter() if default_jitter_s is None else default_jitter_s,
        )
        self._configs: dict[str, _BucketConfig] = {}
        self._next_available: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def configure(self, host: str, *, min_interval_s: float, jitter_s: float) -> None:
        """Override the limiter's defaults for a specific host."""
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be non-negative")
        if jitter_s < 0:
            raise ValueError("jitter_s must be non-negative")
        self._configs[host] = _BucketConfig(min_interval_s, jitter_s)

    async def acquire(self, host: str) -> None:
        """Block until a token is available for `host`."""
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            cfg = self._configs.get(host, self._default)
            now = self._clock()
            next_available = self._next_available.get(host, 0.0)
            wait = next_available - now
            if wait > 0:
                await self._sleep(wait)
                now = self._clock()
            jitter = self._rng() * cfg.jitter_s if cfg.jitter_s > 0 else 0.0
            self._next_available[host] = now + cfg.min_interval_s + jitter
            logger.debug(
                "rate_limiter acquire host=%s waited=%.3fs next_in=%.3fs",
                host,
                max(0.0, wait),
                cfg.min_interval_s + jitter,
            )
