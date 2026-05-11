from fastapi import FastAPI
from fastapi.responses import JSONResponse

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
