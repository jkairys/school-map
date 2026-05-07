"""The OTH client is a deep module — it must not pull in DB code.

Importing the package should not transitively import sqlalchemy, asyncpg,
alembic, or anything under `oth_scraper.db`. If this test fails, something
in the client started reaching for the database; back it out.
"""

import importlib
import sys


FORBIDDEN_PREFIXES = ("sqlalchemy", "asyncpg", "alembic", "oth_scraper.db")


def test_oth_client_import_is_db_free() -> None:
    # Drop any pre-imported forbidden modules so this test is meaningful even
    # when run after another test in the session has imported them.
    for name in list(sys.modules):
        if name.startswith(FORBIDDEN_PREFIXES):
            del sys.modules[name]
    # Drop the client itself so we re-trigger its import side effects.
    for name in list(sys.modules):
        if name.startswith("oth_scraper.oth_client"):
            del sys.modules[name]

    importlib.import_module("oth_scraper.oth_client")

    leaked = sorted(
        name for name in sys.modules if name.startswith(FORBIDDEN_PREFIXES)
    )
    assert not leaked, f"oth_client transitively imported DB modules: {leaked}"
