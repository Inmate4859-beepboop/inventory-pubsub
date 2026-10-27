import sqlalchemy as sa

metadata = sa.MetaData()

stock_events = sa.Table(
    "stock_events",
    metadata,
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
    sa.Index("ix_stock_events_warehouse_sku", "warehouse", "sku"),
)

stock_agg = sa.Table(
    "stock_agg",
    metadata,
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
