"""The OTH client is a deep module — it must not pull in DB code.

Importing the package should not transitively import sqlalchemy, asyncpg,
alembic, or anything under `listings_scraper.db`. If this test fails, something
in the client started reaching for the database; back it out.

Note: we snapshot and restore sys.modules around the import. Removing C
extensions like asyncpg from sys.modules and letting later tests re-import
them can corrupt their compiled state and segfault subsequent postgres
connections — which is exactly what happens when a later test reaches for
asyncpg via SQLAlchemy.
"""

import importlib
import sys


FORBIDDEN_PREFIXES = ("sqlalchemy", "asyncpg", "alembic", "listings_scraper.db")


def test_oth_client_import_is_db_free() -> None:
    saved = {
        name: sys.modules[name]
        for name in list(sys.modules)
        if name.startswith(FORBIDDEN_PREFIXES)
        or name.startswith("listings_scraper.oth_client")
    }
    # Drop forbidden modules so a fresh import of oth_client genuinely
    # exercises its import surface, not the cache.
    for name in list(saved):
        del sys.modules[name]

    try:
        importlib.import_module("listings_scraper.oth_client")
        leaked = sorted(
            name for name in sys.modules if name.startswith(FORBIDDEN_PREFIXES)
        )
        assert not leaked, f"oth_client transitively imported DB modules: {leaked}"
    finally:
        # Restore the original module objects so later tests reuse the same
        # asyncpg C-extension state instead of re-initialising it.
        for name, module in saved.items():
            sys.modules[name] = module
