from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from oth_scraper.api.routers import (
    jobs,
    listings,
    maintenance,
    properties,
    scrape_lists,
    scrape_runs,
    suburbs,
)

app = FastAPI(title="OTH Scraper", version="0.1.0")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(suburbs.router, prefix="/suburbs", tags=["suburbs"])
app.include_router(
    scrape_lists.router, prefix="/scrape-lists", tags=["scrape-lists"]
)
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(
    scrape_runs.router, prefix="/scrape-runs", tags=["scrape-runs"]
)
app.include_router(
    properties.router, prefix="/properties", tags=["properties"]
)
app.include_router(listings.router, prefix="/listings", tags=["listings"])
app.include_router(
    maintenance.router, prefix="/maintenance", tags=["maintenance"]
)

# Mount the admin SPA bundle at /admin/ if the static directory has been built.
# The directory is produced by `task build` in apps/oth-admin/ and intentionally
# not committed to git (see .gitignore). The conditional mount means the backend
# still starts cleanly during development before the SPA has been compiled.
# __file__ = .../services/oth-scraper/src/oth_scraper/api/app.py
# 4 × .parent  → services/oth-scraper/
_ADMIN_STATIC = Path(__file__).parent.parent.parent.parent / "static" / "admin"
if _ADMIN_STATIC.is_dir():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_STATIC), html=True), name="admin")
