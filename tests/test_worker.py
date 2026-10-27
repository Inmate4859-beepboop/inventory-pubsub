import json
import logging

import pytest
import sqlalchemy as sa
from aiohttp.test_utils import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from analytics_worker.handlers import handle_message
from tests.conftest import FakePublisher


def event_bytes(event_id: str, type_: str, qty: int) -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "type": type_,
            "warehouse": "WH-1",
            "sku": "A-100",
            "qty": qty,
            "occurred_at": "2026-10-26T10:00:00Z",
        }
    ).encode()


RECEIPT_50 = event_bytes("11111111-1111-1111-1111-111111111111", "inventory.receipt", 50)
ISSUE_20 = event_bytes("22222222-2222-2222-2222-222222222222", "inventory.issue", 20)


async def handle(conn: AsyncConnection, raw: bytes) -> None:
    await handle_message(conn, raw)
    await conn.commit()


async def stock_agg_rows(engine: AsyncEngine) -> list[tuple[str, str, int]]:
    async with engine.connect() as conn:
        result = await conn.execute(sa.text("SELECT warehouse, sku, qty FROM stock_agg"))
        return [tuple(row) for row in result]


async def test_worker_upserts_stock_agg(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await handle(conn, RECEIPT_50)
        assert await stock_agg_rows(engine) == [("WH-1", "A-100", 50)]

        await handle(conn, ISSUE_20)
        assert await stock_agg_rows(engine) == [("WH-1", "A-100", 30)]


async def test_worker_skips_broken_message(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    broken = [
        b"{not json",
        event_bytes("33333333-3333-3333-3333-333333333333", "inventory.receipt", -5),
        event_bytes("44444444-4444-4444-4444-444444444444", "inventory.transfer", 10),
    ]

    async with engine.connect() as conn:
        await handle(conn, RECEIPT_50)

        for raw in broken:
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                await handle(conn, raw)
            assert any(r.levelno == logging.WARNING for r in caplog.records), raw
            assert await stock_agg_rows(engine) == [("WH-1", "A-100", 50)]

        await handle(conn, ISSUE_20)

    assert await stock_agg_rows(engine) == [("WH-1", "A-100", 30)]


async def test_api_event_is_consumable_by_worker(
    client: TestClient, engine: AsyncEngine, publisher: FakePublisher
) -> None:
    for path, qty in (("/receipts", 50), ("/issues", 20)):
        resp = await client.post(path, json={"warehouse": "WH-1", "sku": "A-100", "qty": qty})
        assert resp.status == 201, await resp.text()

    async with engine.connect() as conn:
        for _, message in publisher.sent:
            await handle(conn, message.encode())

    assert await stock_agg_rows(engine) == [("WH-1", "A-100", 30)]
