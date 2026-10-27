from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

RECEIPT_CHANNEL = "inventory.receipt"
ISSUE_CHANNEL = "inventory.issue"
CHANNELS = (RECEIPT_CHANNEL, ISSUE_CHANNEL)

# op_type в stock_events -> канал / поле type события
OP_TYPE_TO_CHANNEL: dict[str, str] = {
    "receipt": RECEIPT_CHANNEL,
    "issue": ISSUE_CHANNEL,
}


class InventoryEvent(BaseModel):
    event_id: UUID
    type: Literal["inventory.receipt", "inventory.issue"]
    warehouse: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    qty: int = Field(gt=0)
    occurred_at: datetime
