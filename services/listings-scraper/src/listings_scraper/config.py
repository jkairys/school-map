from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://oth:oth@localhost:5432/oth"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # CLI talks to the running api over HTTP — never opens its own DB session.
    # Override via OTH_SCRAPER_BASE_URL when running outside the default loopback.
    scraper_base_url: str = "http://127.0.0.1:8000"
    worker_concurrency: int = 3
    # How long the worker sleeps between empty `claim_next()` polls when the
    # queue has no work. Kept tight (seconds) because Postgres `SKIP LOCKED`
    # claims are cheap and a worker that just finished a job should pick up
    # the next one with minimal latency.
    worker_poll_interval_seconds: float = 1.0
    # Hard deadline applied after SIGTERM: in-flight jobs get this many
    # seconds to drain before the worker exits anyway.
    worker_shutdown_grace_seconds: float = 30.0
    session_max_requests: int = 50
    session_max_age_seconds: int = 1800
    rate_limit_min_interval: float = 1.5
    rate_limit_max_interval: float = 3.0
    # Listings whose `last_seen_at` is older than this window are closed by
    # the soft-expiry sweep that runs at the end of a successful job. The
    # default (14 days) covers ~3 missed scrapes at a daily cadence; tune
    # down for more aggressive closure or up to be more forgiving of
    # anti-bot hiccups.
    soft_expiry_days: int = 14

    # Job queue retry policy. The queue module increments attempts on each
    # fail() call; once attempts > the per-class limit the job dead-letters.
    # See listings_scraper.queue for the lookup logic.
    queue_retry_max_transient: int = 3
    queue_retry_max_antibot: int = 1
    queue_retry_max_parse: int = 0
    # Reclaim TTL: a `running` job whose claimed_at is older than this is
    # considered abandoned and is re-claimable by claim_next().
    queue_reclaim_ttl_seconds: int = 600


settings = Settings()
