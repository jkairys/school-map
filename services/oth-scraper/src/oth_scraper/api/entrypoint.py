import uvicorn
from oth_scraper.api.app import app
from oth_scraper.config import settings


def main() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
