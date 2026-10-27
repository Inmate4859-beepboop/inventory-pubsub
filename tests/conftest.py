from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from aiohttp.test_utils import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from common.config import Settings
from inventory_api.app import create_app

ROOT = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = Settings().test_database_url


class FakePublisher:
    """Заглушка Redis: запоминает, что и в какой канал опубликовано."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        self.sent.append((channel, message))
        return 1


@pytest.fixture(scope="session", autouse=True)
def apply_migrations() -> None:
    # Config без alembic.ini: иначе env.py вызовет fileConfig и отключит
    # уже созданные логгеры приложения — caplog перестанет видеть warning.
    # Фикстура синхронная, потому что env.py сам запускает asyncio.run.
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(sa.text("TRUNCATE stock_events, stock_agg RESTART IDENTITY"))
    yield engine
    await engine.dispose()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
async def client(
    engine: AsyncEngine,
    publisher: FakePublisher,
    aiohttp_client: Callable[..., Awaitable[TestClient]],
) -> TestClient:
    app = create_app(Settings(database_url=TEST_DATABASE_URL), publisher=publisher)
    return await aiohttp_client(app)
