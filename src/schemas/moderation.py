import uuid
from typing import Optional, List
from pydantic import BaseModel
from enum import Enum


class ModerationStatus(str, Enum):
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"


class BlockingReason(BaseModel):
    id: uuid.UUID
    title: str
    comment: str


class FieldReport(BaseModel):
    field_name: str
    sku_id: Optional[uuid.UUID] = None
    comment: str


class ModerationEvent(BaseModel):
    idempotency_key: uuid.UUID
    product_id: uuid.UUID
    status: ModerationStatus
    hard_block: bool = False
    blocking_reason: Optional[BlockingReason] = None
    field_reports: Optional[List[FieldReport]] = []
