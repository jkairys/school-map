import uvicorn
from listings_scraper.api.app import app
from listings_scraper.config import settings


def main() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
