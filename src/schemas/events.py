"""
Pydantic-схемы для входящих событий от Moderation.
Формат по протоколу: ModerationEventRequest.
"""

import uuid

from pydantic import BaseModel, Field


class FieldReport(BaseModel):
    """Замечание по конкретному полю товара/SKU."""
    field_name: str
    sku_id: uuid.UUID | None = None
    comment: str


class ModerationEventRequest(BaseModel):
    """
    POST /api/v1/moderation/events — входящее событие от Moderation.
    event_type: MODERATED или BLOCKED.
    При BLOCKED: blocking_reason_id обязателен, hard_block определяет soft/hard.
    """
    idempotency_key: uuid.UUID
    product_id: uuid.UUID
    event_type: str  # MODERATED | BLOCKED
    moderator_id: uuid.UUID | None = None
    moderator_comment: str | None = None
    blocking_reason_id: uuid.UUID | None = None
    hard_block: bool = False
    field_reports: list[FieldReport] | None = None
    occurred_at: str
