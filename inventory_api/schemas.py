from pydantic import BaseModel, ConfigDict, Field

# stock_events.qty — integer (int4), больше в колонку не влезет
MAX_QTY = 2_147_483_647


class OperationIn(BaseModel):
    """Тело POST /receipts и POST /issues."""

    # strict: "50" и 50.5 не превращаются молча в 50; forbid: опечатка в имени поля -> 400
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)

    warehouse: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    qty: int = Field(gt=0, le=MAX_QTY)


class StockQuery(BaseModel):
    """Query-параметры GET /stock."""

    model_config = ConfigDict(str_strip_whitespace=True)

    warehouse: str = Field(min_length=1)
    sku: str | None = Field(default=None, min_length=1)


class SummaryQuery(BaseModel):
    """Query-параметры GET /stock/summary. Без strict: из query-строки приходит "5", а не 5."""

    top_n: int = Field(default=5, ge=1, le=100)
