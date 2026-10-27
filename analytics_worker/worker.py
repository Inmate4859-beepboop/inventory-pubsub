import asyncio
import logging
import signal

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from analytics_worker.handlers import handle_message
from common.config import Settings
from common.events import CHANNELS

logger = logging.getLogger(__name__)

# Сколько get_message ждёт сообщение. Раз в столько секунд цикл проверяет флаг остановки.
POLL_TIMEOUT = 1.0


def install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows: у event loop нет add_signal_handler. Обычный обработчик сигнала
            # не должен трогать loop напрямую, поэтому через call_soon_threadsafe.
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))


async def process_message(engine: AsyncEngine, message: dict) -> None:
    try:
        async with engine.begin() as conn:
            await handle_message(conn, message["data"])
    except Exception:
        # Ошибка одного сообщения (например, БД недоступна) не должна останавливать цикл
        logger.exception("Failed to process message from %s", message["channel"])


async def run_worker(settings: Settings, stop: asyncio.Event) -> None:
    engine = create_async_engine(settings.database_url)
    client = redis.from_url(settings.redis_url)
    # PubSub берёт из пула отдельное соединение: в режиме подписки оно не выполняет других команд
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(*CHANNELS)
        logger.info("Subscribed to %s", ", ".join(CHANNELS))

        while not stop.is_set():
            message = await pubsub.get_message(timeout=POLL_TIMEOUT)
            if message is None:
                continue  # таймаут: сообщений не было, идём проверить stop
            if message["type"] != "message":
                continue  # служебные: subscribe / unsubscribe
            await process_message(engine, message)
    finally:
        logger.info("Shutting down")
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await client.aclose()
        await engine.dispose()
        logger.info("Stopped")
