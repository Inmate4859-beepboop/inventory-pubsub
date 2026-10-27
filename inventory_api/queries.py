from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection

from common.db import stock_events

# Знаковое количество: приход +qty, расход -qty. Основа всех расчётов остатков.
signed_qty = sa.case(
    (stock_events.c.op_type == "receipt", stock_events.c.qty),
    else_=-stock_events.c.qty,
)


async def lock_pair(conn: AsyncConnection, warehouse: str, sku: str) -> None:
    """Блокировка пары (warehouse, sku) до конца текущей транзакции.

    Вариант с двумя int-ключами: склейка строк дала бы один ключ для
    ("A", "BC") и ("AB", "C").
    """
    await conn.execute(
        sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext(warehouse), sa.func.hashtext(sku)))
    )


async def get_balance(conn: AsyncConnection, warehouse: str, sku: str) -> int:
    query = sa.select(sa.func.coalesce(sa.func.sum(signed_qty), 0)).where(
        stock_events.c.warehouse == warehouse,
        stock_events.c.sku == sku,
    )
    return int(await conn.scalar(query))


async def insert_operation(
    conn: AsyncConnection,
    *,
    event_id: UUID,
    warehouse: str,
    sku: str,
    op_type: str,
    qty: int,
) -> Row:
    query = (
        sa.insert(stock_events)
        .values(event_id=event_id, warehouse=warehouse, sku=sku, op_type=op_type, qty=qty)
        .returning(*stock_events.c)
    )
    result = await conn.execute(query)
    return result.one()


async def get_stock(conn: AsyncConnection, warehouse: str, sku: str | None = None) -> list[Row]:
    query = (
        sa.select(
            stock_events.c.warehouse,
            stock_events.c.sku,
            sa.func.sum(signed_qty).label("qty"),
        )
        .where(stock_events.c.warehouse == warehouse)
        .group_by(stock_events.c.warehouse, stock_events.c.sku)
        .order_by(stock_events.c.sku)
    )
    if sku is not None:
        query = query.where(stock_events.c.sku == sku)
    result = await conn.execute(query)
    return list(result.all())


def balances_subquery() -> sa.Subquery:
    """Остаток по каждой паре (warehouse, sku) — основа для summary."""
    return (
        sa.select(
            stock_events.c.warehouse,
            stock_events.c.sku,
            sa.func.sum(signed_qty).label("qty"),
        )
        .group_by(stock_events.c.warehouse, stock_events.c.sku)
        .subquery("balances")
    )


async def get_summary(conn: AsyncConnection, top_n: int) -> tuple[list[Row], list[Row]]:
    """Сводка по складам и топ SKU по всем складам.

    SELECT warehouse, SUM(qty) AS total_qty, COUNT(*) FILTER (WHERE qty > 0) AS sku_count
    FROM (<balances>) AS balances
    GROUP BY warehouse ORDER BY warehouse;

    SELECT sku, SUM(qty) AS total_qty
    FROM (<balances>) AS balances
    GROUP BY sku HAVING SUM(qty) > 0
    ORDER BY total_qty DESC, sku LIMIT :top_n;
    """
    balances = balances_subquery()
    # SUM(bigint) в Postgres возвращает numeric -> Decimal в Python, json.dumps его не умеет
    total_qty = sa.cast(sa.func.sum(balances.c.qty), sa.BigInteger).label("total_qty")

    warehouses_query = (
        sa.select(
            balances.c.warehouse,
            total_qty,
            sa.func.count().filter(balances.c.qty > 0).label("sku_count"),
        )
        .group_by(balances.c.warehouse)
        .order_by(balances.c.warehouse)
    )
    top_skus_query = (
        sa.select(balances.c.sku, total_qty)
        .group_by(balances.c.sku)
        .having(sa.func.sum(balances.c.qty) > 0)
        .order_by(total_qty.desc(), balances.c.sku)
        .limit(top_n)
    )

    warehouses = list((await conn.execute(warehouses_query)).all())
    top_skus = list((await conn.execute(top_skus_query)).all())
    return warehouses, top_skus
