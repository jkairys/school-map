"""Worker process entrypoint.

Thin wrapper around `listings_scraper.worker_loop.run_worker` that configures
logging and runs the asyncio loop. The real loop, error classification,
and signal handling live in `worker_loop.loop`.
"""
import asyncio
import logging

from listings_scraper.worker_loop import run_worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
