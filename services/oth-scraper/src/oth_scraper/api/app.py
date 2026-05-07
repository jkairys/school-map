from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="OTH Scraper", version="0.1.0")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# Placeholder routers — populated by later issues
# from oth_scraper.api.routers import scrape_lists, jobs, properties, listings
# app.include_router(scrape_lists.router, prefix="/scrape-lists")
# app.include_router(jobs.router, prefix="/jobs")
# app.include_router(properties.router, prefix="/properties")
# app.include_router(listings.router, prefix="/listings")
