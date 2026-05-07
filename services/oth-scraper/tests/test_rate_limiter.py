import asyncio

import pytest

from oth_scraper.rate_limiter import RateLimiter


class MockClock:
    """A deterministic clock + sleep pair for driving the limiter under test.

    `sleep(dt)` advances the simulated time by `dt` and yields to the event
    loop so other waiters scheduled by `asyncio.Lock` can run. Tests never
    block on real wall-clock time.
    """

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t

    async def sleep(self, dt: float) -> None:
        if dt > 0:
            self.t += dt
        # Yield repeatedly so any tasks unblocked by the lock release get
        # a chance to progress before we return to the caller.
        for _ in range(3):
            await asyncio.sleep(0)


async def _drain():
    """Yield enough times for any pending tasks to settle."""
    for _ in range(5):
        await asyncio.sleep(0)


async def test_serial_acquires_respect_min_interval():
    clock = MockClock()
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        default_min_interval_s=1.0,
        default_jitter_s=0.0,
    )

    timestamps: list[float] = []
    for _ in range(5):
        await limiter.acquire("host.example")
        timestamps.append(clock.now())

    assert timestamps == [0.0, 1.0, 2.0, 3.0, 4.0]


async def test_ten_concurrent_acquires_complete_in_expected_time():
    clock = MockClock()
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        default_min_interval_s=1.0,
        default_jitter_s=0.0,
    )

    completion_times: list[float] = []

    async def worker():
        await limiter.acquire("onthehouse.com.au")
        completion_times.append(clock.now())

    await asyncio.gather(*(worker() for _ in range(10)))

    # First task fires at t=0, then one per 1.0s — last completes at t=9.0.
    assert completion_times == sorted(completion_times)
    assert completion_times[0] == pytest.approx(0.0)
    assert completion_times[-1] == pytest.approx(9.0)
    # Adjacent intervals are exactly 1.0s.
    intervals = [b - a for a, b in zip(completion_times, completion_times[1:])]
    for gap in intervals:
        assert gap == pytest.approx(1.0)


async def test_jitter_keeps_intervals_within_window():
    clock = MockClock()
    # Cycle through a few RNG values to spread observed intervals.
    rng_values = iter([0.0, 0.25, 0.5, 0.75, 0.99] * 20)
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: next(rng_values),
        default_min_interval_s=1.0,
        default_jitter_s=0.5,
    )

    timestamps: list[float] = []
    for _ in range(50):
        await limiter.acquire("host.example")
        timestamps.append(clock.now())

    intervals = [b - a for a, b in zip(timestamps, timestamps[1:])]
    assert intervals, "expected observed intervals"
    for gap in intervals:
        assert 1.0 <= gap <= 1.5 + 1e-9, f"interval {gap} outside [1.0, 1.5]"

    # Sanity: with varied RNG we should see more than one distinct interval.
    assert len({round(g, 4) for g in intervals}) > 1


async def test_independent_buckets_per_host():
    clock = MockClock()
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        default_min_interval_s=10.0,
        default_jitter_s=0.0,
    )

    await limiter.acquire("a")
    t_after_a = clock.now()
    await limiter.acquire("b")
    t_after_b = clock.now()

    # Acquiring on host "b" must not wait on host "a"'s bucket.
    assert t_after_a == pytest.approx(0.0)
    assert t_after_b == pytest.approx(0.0)


async def test_per_host_configure_overrides_default():
    clock = MockClock()
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        default_min_interval_s=1.0,
        default_jitter_s=0.0,
    )
    limiter.configure("slow.example", min_interval_s=5.0, jitter_s=0.0)

    # Fast host: default 1.0s spacing.
    await limiter.acquire("fast.example")
    await limiter.acquire("fast.example")
    fast_elapsed = clock.now()
    assert fast_elapsed == pytest.approx(1.0)

    # Slow host: 5.0s spacing, on its own bucket so it starts at 0.
    clock.t = 0.0
    await limiter.acquire("slow.example")
    await limiter.acquire("slow.example")
    slow_elapsed = clock.now()
    assert slow_elapsed == pytest.approx(5.0)


async def test_acquire_does_not_wait_when_bucket_is_idle():
    clock = MockClock(t=100.0)
    limiter = RateLimiter(
        clock=clock.now,
        sleep=clock.sleep,
        rng=lambda: 0.0,
        default_min_interval_s=2.0,
        default_jitter_s=0.0,
    )

    await limiter.acquire("host.example")
    assert clock.now() == pytest.approx(100.0)  # no wait on first call

    # Idle past next_available — next call must not wait.
    clock.t = 200.0
    await limiter.acquire("host.example")
    assert clock.now() == pytest.approx(200.0)


async def test_configure_rejects_negative_values():
    limiter = RateLimiter()
    with pytest.raises(ValueError):
        limiter.configure("h", min_interval_s=-1.0, jitter_s=0.0)
    with pytest.raises(ValueError):
        limiter.configure("h", min_interval_s=1.0, jitter_s=-0.5)
