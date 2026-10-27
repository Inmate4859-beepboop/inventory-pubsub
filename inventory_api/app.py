from collections.abc import AsyncIterator
from typing import Protocol

import redis.asyncio as redis
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.config import Settings


class Publisher(Protocol):
    """Всё, что API нужно от Redis. В тестах подменяется заглушкой."""

    async def publish(self, channel: str, message: str) -> int: ...


engine_key = web.AppKey("engine", AsyncEngine)
publisher_key = web.AppKey("publisher", Publisher)


def create_app(settings: Settings, publisher: Publisher | None = None) -> web.Application:
    from inventory_api.handlers import routes

    app = web.Application()
    app.add_routes(routes)

    async def engine_ctx(app: web.Application) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url)
        app[engine_key] = engine
        yield
        await engine.dispose()

    async def publisher_ctx(app: web.Application) -> AsyncIterator[None]:
        if publisher is not None:
            # Заглушку создал и закрывает тот, кто её передал
            app[publisher_key] = publisher
            yield
            return
        client = redis.from_url(settings.redis_url)
        app[publisher_key] = client
        yield
        await client.aclose()

    app.cleanup_ctx.append(engine_ctx)
    app.cleanup_ctx.append(publisher_ctx)
    return app
