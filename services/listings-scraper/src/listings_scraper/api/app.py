from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from listings_scraper.api.routers import (
    jobs,
    listings,
    maintenance,
    properties,
    scrape_lists,
    scrape_runs,
    suburbs,
)

app = FastAPI(title="Listings Scraper", version="0.4.0")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# /v1/ routes — canonical paths for new code
# ---------------------------------------------------------------------------
app.include_router(suburbs.router, prefix="/v1/suburbs", tags=["suburbs"])
app.include_router(
    scrape_lists.router, prefix="/v1/scrape-lists", tags=["scrape-lists"]
)
app.include_router(jobs.router, prefix="/v1/jobs", tags=["jobs"])
app.include_router(
    scrape_runs.router, prefix="/v1/scrape-runs", tags=["scrape-runs"]
)
app.include_router(
    properties.router, prefix="/v1/properties", tags=["properties"]
)
app.include_router(listings.router, prefix="/v1/listings", tags=["listings"])
app.include_router(
    maintenance.router, prefix="/v1/maintenance", tags=["maintenance"]
)

# ---------------------------------------------------------------------------
# Legacy unversioned paths — deprecated; will be removed in a future release.
# Keep alive for one release cycle so existing clients have time to migrate.
# New code should use /v1/... paths.
# ---------------------------------------------------------------------------
app.include_router(suburbs.router, prefix="/suburbs", tags=["suburbs (deprecated)"])
app.include_router(
    scrape_lists.router,
    prefix="/scrape-lists",
    tags=["scrape-lists (deprecated)"],
)
app.include_router(jobs.router, prefix="/jobs", tags=["jobs (deprecated)"])
app.include_router(
    scrape_runs.router,
    prefix="/scrape-runs",
    tags=["scrape-runs (deprecated)"],
)
app.include_router(
    properties.router,
    prefix="/properties",
    tags=["properties (deprecated)"],
)
app.include_router(
    listings.router, prefix="/listings", tags=["listings (deprecated)"]
)
app.include_router(
    maintenance.router,
    prefix="/maintenance",
    tags=["maintenance (deprecated)"],
)

# Mount the admin SPA bundle at /admin/ if the static directory has been built.
# The directory is produced by `task build` in apps/oth-admin/ and intentionally
# not committed to git (see .gitignore). The conditional mount means the backend
# still starts cleanly during development before the SPA has been compiled.
# __file__ = .../services/listings-scraper/src/listings_scraper/api/app.py
# 4 × .parent  → services/listings-scraper/
_ADMIN_STATIC = Path(__file__).parent.parent.parent.parent / "static" / "admin"
if _ADMIN_STATIC.is_dir():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_STATIC), html=True), name="admin")
