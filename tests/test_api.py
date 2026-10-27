import json
from typing import Any

import sqlalchemy as sa
from aiohttp.test_utils import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import FakePublisher


async def post_op(client: TestClient, path: str, warehouse: str, sku: str, qty: int) -> Any:
    resp = await client.post(path, json={"warehouse": warehouse, "sku": sku, "qty": qty})
    assert resp.status == 201, await resp.text()
    return await resp.json()


async def get_items(client: TestClient, **params: str) -> list[dict[str, Any]]:
    resp = await client.get("/stock", params=params)
    assert resp.status == 200, await resp.text()
    body = await resp.json()
    return sorted(body["items"], key=lambda i: (i["warehouse"], i["sku"]))


async def test_receipt_and_issue_update_stock(
    client: TestClient, engine: AsyncEngine, publisher: FakePublisher
) -> None:
    first = await post_op(client, "/receipts", "WH-1", "A-100", 50)
    await post_op(client, "/issues", "WH-1", "A-100", 20)
    await post_op(client, "/receipts", "WH-1", "B-200", 5)
    await post_op(client, "/receipts", "WH-2", "A-100", 7)

    assert first["warehouse"] == "WH-1"
    assert first["sku"] == "A-100"
    assert first["op_type"] == "receipt"
    assert first["qty"] == 50

    assert await get_items(client, warehouse="WH-1", sku="A-100") == [
        {"warehouse": "WH-1", "sku": "A-100", "qty": 30},
    ]
    assert await get_items(client, warehouse="WH-1") == [
        {"warehouse": "WH-1", "sku": "A-100", "qty": 30},
        {"warehouse": "WH-1", "sku": "B-200", "qty": 5},
    ]

    async with engine.connect() as conn:
        rows = (
            await conn.execute(sa.text("SELECT event_id, op_type, qty FROM stock_events ORDER BY id"))
        ).all()
    assert [(r.op_type, r.qty) for r in rows] == [
        ("receipt", 50),
        ("issue", 20),
        ("receipt", 5),
        ("receipt", 7),
    ]

    assert len(publisher.sent) == 4
    assert publisher.sent[0][0] == "inventory.receipt"
    channel, message = publisher.sent[1]
    assert channel == "inventory.issue"
    event = json.loads(message)
    assert event["type"] == "inventory.issue"
    assert event["warehouse"] == "WH-1"
    assert event["sku"] == "A-100"
    assert event["qty"] == 20
    assert event["event_id"] == str(rows[1].event_id)
    assert "occurred_at" in event


async def test_issue_more_than_stock_returns_409(
    client: TestClient, engine: AsyncEngine, publisher: FakePublisher
) -> None:
    await post_op(client, "/receipts", "WH-1", "A-100", 10)

    resp = await client.post("/issues", json={"warehouse": "WH-1", "sku": "A-100", "qty": 11})
    assert resp.status == 409
    assert (await resp.json())["error"] == "insufficient_stock"

    async with engine.connect() as conn:
        count = await conn.scalar(sa.text("SELECT count(*) FROM stock_events"))
    assert count == 1
    assert [channel for channel, _ in publisher.sent] == ["inventory.receipt"]
    assert await get_items(client, warehouse="WH-1", sku="A-100") == [
        {"warehouse": "WH-1", "sku": "A-100", "qty": 10},
    ]


async def test_invalid_input_returns_400(
    client: TestClient, engine: AsyncEngine, publisher: FakePublisher
) -> None:
    resp = await client.post("/receipts", json={"warehouse": "WH-1", "sku": "A-100", "qty": 0})
    assert resp.status == 400
    assert (await resp.json())["error"] == "validation_error"

    resp = await client.post("/issues", json={"warehouse": "WH-1", "qty": 5})
    assert resp.status == 400

    resp = await client.get("/stock")
    assert resp.status == 400

    async with engine.connect() as conn:
        count = await conn.scalar(sa.text("SELECT count(*) FROM stock_events"))
    assert count == 0
    assert publisher.sent == []


async def test_stock_summary(client: TestClient) -> None:
    operations = [
        ("/receipts", "WH-1", "A-100", 100),
        ("/receipts", "WH-1", "B-200", 40),
        ("/receipts", "WH-1", "C-300", 10),
        ("/issues", "WH-1", "C-300", 10),
        ("/receipts", "WH-2", "A-100", 30),
        ("/receipts", "WH-2", "B-200", 70),
        ("/receipts", "WH-2", "D-400", 5),
        ("/receipts", "WH-2", "E-500", 3),
        ("/receipts", "WH-2", "F-600", 2),
        ("/receipts", "WH-2", "G-700", 1),
    ]
    for path, warehouse, sku, qty in operations:
        await post_op(client, path, warehouse, sku, qty)

    resp = await client.get("/stock/summary", params={"top_n": "2"})
    assert resp.status == 200
    body = await resp.json()
    assert sorted(body["warehouses"], key=lambda w: w["warehouse"]) == [
        {"warehouse": "WH-1", "total_qty": 140, "sku_count": 2},
        {"warehouse": "WH-2", "total_qty": 111, "sku_count": 6},
    ]
    assert body["top_skus"] == [
        {"sku": "A-100", "total_qty": 130},
        {"sku": "B-200", "total_qty": 110},
    ]

    resp = await client.get("/stock/summary")
    assert resp.status == 200
    assert (await resp.json())["top_skus"] == [
        {"sku": "A-100", "total_qty": 130},
        {"sku": "B-200", "total_qty": 110},
        {"sku": "D-400", "total_qty": 5},
        {"sku": "E-500", "total_qty": 3},
        {"sku": "F-600", "total_qty": 2},
    ]
