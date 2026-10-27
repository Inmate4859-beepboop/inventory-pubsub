import logging

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from common.db import stock_agg
from common.events import RECEIPT_CHANNEL, InventoryEvent

logger = logging.getLogger(__name__)


async def upsert_stock_agg(conn: AsyncConnection, warehouse: str, sku: str, delta: int) -> None:
    """INSERT ... ON CONFLICT (warehouse, sku) DO UPDATE SET qty = stock_agg.qty + excluded.qty"""
    stmt = insert(stock_agg).values(warehouse=warehouse, sku=sku, qty=delta)
    stmt = stmt.on_conflict_do_update(
        index_elements=[stock_agg.c.warehouse, stock_agg.c.sku],
        set_={
            "qty": stock_agg.c.qty + stmt.excluded.qty,
            # server_default срабатывает только на INSERT, при обновлении ставим время сами
            "updated_at": sa.func.now(),
        },
    )
    await conn.execute(stmt)


def describe_errors(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, err['loc'])) or '<root>'}: {err['msg']}" for err in exc.errors()
    )


async def handle_message(conn: AsyncConnection, raw: str | bytes) -> bool:
    """Обработать одно сообщение из Redis. Транзакцией управляет вызывающий.

    Возвращает False, если сообщение невалидно и пропущено.
    """
    try:
        event = InventoryEvent.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Skipping invalid event (%s): %.200r", describe_errors(exc), raw)
        return False

    delta = event.qty if event.type == RECEIPT_CHANNEL else -event.qty
    await upsert_stock_agg(conn, event.warehouse, event.sku, delta)
    logger.info(
        "Applied %s %s/%s %+d (event_id=%s)",
        event.type, event.warehouse, event.sku, delta, event.event_id,
    )
    return True
