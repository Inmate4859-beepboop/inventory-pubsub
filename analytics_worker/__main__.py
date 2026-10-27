import asyncio
import logging

from analytics_worker.worker import install_signal_handlers, run_worker
from common.config import get_settings


async def main() -> None:
    stop = asyncio.Event()
    install_signal_handlers(stop)
    await run_worker(get_settings(), stop)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
