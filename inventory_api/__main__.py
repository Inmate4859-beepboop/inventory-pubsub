import logging

from common.config import get_settings

logger = logging.getLogger("inventory_api")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    logger.info("inventory_api starting (port=%s)", settings.api_port)


if __name__ == "__main__":
    main()
