"""Per-host token-bucket rate limiter for the OTH scraper.

Cross-process coordination is intentionally out of scope: v1 runs a single
worker process. If a v2 ever scales to multiple workers, replace this with
a shared store (Redis, Postgres advisory lock) — do not bolt one on here.
"""

from listings_scraper.rate_limiter.limiter import RateLimiter

__all__ = ["RateLimiter"]
