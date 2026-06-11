import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import os

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow OTH_DATABASE_URL env var to override alembic.ini (used in Docker)
db_url = os.environ.get("OTH_DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Import Base so Alembic can detect model changes in future migrations.
# Importing the models package registers all models on Base.metadata.
from listings_scraper.db.engine import Base  # noqa: E402
from listings_scraper.db import models  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
