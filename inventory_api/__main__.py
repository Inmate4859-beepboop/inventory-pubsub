import logging

from aiohttp import web

from common.config import get_settings
from inventory_api.app import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    web.run_app(create_app(settings), port=settings.api_port)


if __name__ == "__main__":
    main()
