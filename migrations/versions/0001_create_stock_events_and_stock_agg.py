"""create stock_events and stock_agg

Revision ID: 0001
Revises: 
Create Date: 2026-10-26 12:14:20.469247

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Миграция намеренно не импортирует common.db: она фиксирует схему на момент
    # этой ревизии и не должна меняться, когда меняется metadata.
    op.create_table(
        "stock_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("event_id", sa.Uuid, nullable=False),
        sa.Column("warehouse", sa.Text, nullable=False),
        sa.Column("sku", sa.Text, nullable=False),
        sa.Column("op_type", sa.Text, nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("event_id", name="uq_stock_events_event_id"),
        sa.CheckConstraint("op_type IN ('receipt', 'issue')", name="ck_stock_events_op_type"),
        sa.CheckConstraint("qty > 0", name="ck_stock_events_qty_positive"),
    )
    op.create_index("ix_stock_events_warehouse_sku", "stock_events", ["warehouse", "sku"])

    op.create_table(
        "stock_agg",
        sa.Column("warehouse", sa.Text, nullable=False),
        sa.Column("sku", sa.Text, nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("warehouse", "sku", name="pk_stock_agg"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("stock_agg")
    op.drop_index("ix_stock_events_warehouse_sku", table_name="stock_events")
    op.drop_table("stock_events")
