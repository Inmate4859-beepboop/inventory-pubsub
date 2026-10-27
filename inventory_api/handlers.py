import json
import logging
import uuid
from typing import Any

from aiohttp import web
from pydantic import ValidationError
from sqlalchemy.engine import Row

from common.events import OP_TYPE_TO_CHANNEL, InventoryEvent
from inventory_api import queries
from inventory_api.app import engine_key, publisher_key
from inventory_api.schemas import OperationIn, StockQuery, SummaryQuery

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def validation_error(exc: ValidationError) -> web.Response:
    # exc.json() вместо exc.errors(): в errors() бывают несериализуемые объекты (ctx с исключением)
    details = json.loads(exc.json(include_url=False))
    return web.json_response({"error": "validation_error", "details": details}, status=400)


def operation_to_dict(row: Row) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_id": str(row.event_id),
        "warehouse": row.warehouse,
        "sku": row.sku,
        "op_type": row.op_type,
        "qty": row.qty,
        "created_at": row.created_at.isoformat(),
    }


async def create_operation(request: web.Request, op_type: str) -> web.Response:
    try:
        # model_validate_json сам разбирает JSON: битый JSON тоже придёт как ValidationError
        data = OperationIn.model_validate_json(await request.read())
    except ValidationError as exc:
        return validation_error(exc)

    engine = request.app[engine_key]
    async with engine.begin() as conn:
        if op_type == "issue":
            await queries.lock_pair(conn, data.warehouse, data.sku)
            available = await queries.get_balance(conn, data.warehouse, data.sku)
            if available < data.qty:
                # Выход из begin() без исключения = COMMIT (пустой: мы ничего не писали),
                # на нём же снимается advisory lock

                return web.json_response(
                    {"error": "insufficient_stock", "available": available, "requested": data.qty},
                    status=409,
                )
        row = await queries.insert_operation(
            conn,
            event_id=uuid.uuid4(),
            warehouse=data.warehouse,
            sku=data.sku,
            op_type=op_type,
            qty=data.qty,
        )
    # Здесь транзакция уже закоммичена: публикуем только то, что точно есть в БД

    channel = OP_TYPE_TO_CHANNEL[op_type]
    event = InventoryEvent(
        event_id=row.event_id,
        type=channel,
        warehouse=row.warehouse,
        sku=row.sku,
        qty=row.qty,
        occurred_at=row.created_at,
    )
    try:
        await request.app[publisher_key].publish(channel, event.model_dump_json())
    except Exception:
        # Операция записана, повтор POST создал бы дубль. Событие теряется (dual write, см. README).
        logger.exception("Failed to publish event %s to %s", row.event_id, channel)

    return web.json_response(operation_to_dict(row), status=201)


@routes.post("/receipts")
async def create_receipt(request: web.Request) -> web.Response:
    return await create_operation(request, "receipt")


@routes.post("/issues")
async def create_issue(request: web.Request) -> web.Response:
    return await create_operation(request, "issue")


@routes.get("/stock")
async def get_stock(request: web.Request) -> web.Response:
    try:
        params = StockQuery.model_validate(dict(request.query))
    except ValidationError as exc:
        return validation_error(exc)

    async with request.app[engine_key].connect() as conn:
        rows = await queries.get_stock(conn, params.warehouse, params.sku)

    return web.json_response(
        {"items": [{"warehouse": r.warehouse, "sku": r.sku, "qty": r.qty} for r in rows]}
    )


@routes.get("/stock/summary")
async def get_stock_summary(request: web.Request) -> web.Response:
    try:
        params = SummaryQuery.model_validate(dict(request.query))
    except ValidationError as exc:
        return validation_error(exc)

    async with request.app[engine_key].connect() as conn:
        warehouses, top_skus = await queries.get_summary(conn, params.top_n)

    return web.json_response(
        {
            "warehouses": [
                {"warehouse": r.warehouse, "total_qty": r.total_qty, "sku_count": r.sku_count}
                for r in warehouses
            ],
            "top_skus": [{"sku": r.sku, "total_qty": r.total_qty} for r in top_skus],
        }
    )
