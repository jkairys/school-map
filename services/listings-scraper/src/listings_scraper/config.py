"""Service configuration via pydantic-settings.

Env-var prefix transition (PR 3):
  - New prefix: `LS_` (Listings Scraper)
  - Legacy prefix: `OTH_` (OnTheHouse — preserved for backward compat)

Both prefixes are accepted for all fields via `AliasChoices`. New
deployments and documentation should use `LS_*`. Existing `OTH_*`
environment variables continue to work without any changes.

Example:
  LS_DATABASE_URL or OTH_DATABASE_URL both set `settings.database_url`.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic-settings v2: env_prefix only applies when no alias is set.
    # We use field-level AliasChoices for dual-prefix support.
    # extra="ignore" means unknown env vars are silently dropped.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://oth:oth@localhost:5432/oth",
        validation_alias=AliasChoices("LS_DATABASE_URL", "OTH_DATABASE_URL"),
    )
    api_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("LS_API_HOST", "OTH_API_HOST"),
    )
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("LS_API_PORT", "OTH_API_PORT"),
    )
    # CLI talks to the running api over HTTP — never opens its own DB session.
    # Override via LS_SCRAPER_BASE_URL (or legacy OTH_SCRAPER_BASE_URL).
    scraper_base_url: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias=AliasChoices("LS_SCRAPER_BASE_URL", "OTH_SCRAPER_BASE_URL"),
    )
    worker_concurrency: int = Field(
        default=3,
        validation_alias=AliasChoices("LS_WORKER_CONCURRENCY", "OTH_WORKER_CONCURRENCY"),
    )
    # How long the worker sleeps between empty `claim_next()` polls when the
    # queue has no work. Kept tight (seconds) because Postgres `SKIP LOCKED`
    # claims are cheap and a worker that just finished a job should pick up
    # the next one with minimal latency.
    worker_poll_interval_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "LS_WORKER_POLL_INTERVAL_SECONDS", "OTH_WORKER_POLL_INTERVAL_SECONDS"
        ),
    )
    # Hard deadline applied after SIGTERM: in-flight jobs get this many
    # seconds to drain before the worker exits anyway.
    worker_shutdown_grace_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "LS_WORKER_SHUTDOWN_GRACE_SECONDS", "OTH_WORKER_SHUTDOWN_GRACE_SECONDS"
        ),
    )
    session_max_requests: int = Field(
        default=50,
        validation_alias=AliasChoices(
            "LS_SESSION_MAX_REQUESTS", "OTH_SESSION_MAX_REQUESTS"
        ),
    )
    session_max_age_seconds: int = Field(
        default=1800,
        validation_alias=AliasChoices(
            "LS_SESSION_MAX_AGE_SECONDS", "OTH_SESSION_MAX_AGE_SECONDS"
        ),
    )
    rate_limit_min_interval: float = Field(
        default=1.5,
        validation_alias=AliasChoices(
            "LS_RATE_LIMIT_MIN_INTERVAL", "OTH_RATE_LIMIT_MIN_INTERVAL"
        ),
    )
    rate_limit_max_interval: float = Field(
        default=3.0,
        validation_alias=AliasChoices(
            "LS_RATE_LIMIT_MAX_INTERVAL", "OTH_RATE_LIMIT_MAX_INTERVAL"
        ),
    )
    # Listings whose `last_seen_at` is older than this window are closed by
    # the soft-expiry sweep that runs at the end of a successful job. The
    # default (14 days) covers ~3 missed scrapes at a daily cadence.
    soft_expiry_days: int = Field(
        default=14,
        validation_alias=AliasChoices("LS_SOFT_EXPIRY_DAYS", "OTH_SOFT_EXPIRY_DAYS"),
    )

    # Job queue retry policy.
    queue_retry_max_transient: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "LS_QUEUE_RETRY_MAX_TRANSIENT", "OTH_QUEUE_RETRY_MAX_TRANSIENT"
        ),
    )
    queue_retry_max_antibot: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "LS_QUEUE_RETRY_MAX_ANTIBOT", "OTH_QUEUE_RETRY_MAX_ANTIBOT"
        ),
    )
    queue_retry_max_parse: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "LS_QUEUE_RETRY_MAX_PARSE", "OTH_QUEUE_RETRY_MAX_PARSE"
        ),
    )
    # Reclaim TTL: a `running` job whose claimed_at is older than this is
    # considered abandoned and is re-claimable by claim_next().
    queue_reclaim_ttl_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "LS_QUEUE_RECLAIM_TTL_SECONDS", "OTH_QUEUE_RECLAIM_TTL_SECONDS"
        ),
    )


settings = Settings()
