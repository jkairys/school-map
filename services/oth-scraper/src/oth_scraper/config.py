from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://oth:oth@localhost:5432/oth"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    worker_concurrency: int = 2
    session_max_requests: int = 50
    session_max_age_seconds: int = 1800
    rate_limit_min_interval: float = 1.5
    rate_limit_max_interval: float = 3.0
    soft_expiry_missed_runs: int = 3


settings = Settings()
