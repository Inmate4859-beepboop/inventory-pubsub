import logging

from common.config import get_settings

logger = logging.getLogger("analytics_worker")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    logger.info("analytics_worker starting (redis=%s)", settings.redis_url)


if __name__ == "__main__":
    main()
