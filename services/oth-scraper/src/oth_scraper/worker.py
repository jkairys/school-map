import asyncio
import logging

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    logger.info("Worker started — no work in queue, idling")
    while True:
        await asyncio.sleep(5)
        logger.debug("Worker: no jobs available")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
