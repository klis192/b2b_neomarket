"""
Pydantic-схемы для резервирования/снятия резерва.
Формат по протоколу neomarket-protocols/b2b/openapi.yaml.
"""

import uuid

from pydantic import BaseModel, Field


class InventoryItem(BaseModel):
    """Позиция для reserve/unreserve/fulfill."""
    sku_id: uuid.UUID
    quantity: int = Field(..., ge=1)


class ReserveRequest(BaseModel):
    """POST /api/v1/inventory/reserve — all-or-nothing резервирование."""
    idempotency_key: uuid.UUID
    order_id: uuid.UUID
    items: list[InventoryItem] = Field(..., min_length=1)


class ReserveResponse(BaseModel):
    """Успешный ответ резервирования."""
    order_id: str
    status: str = "RESERVED"
    reserved_at: str


class InventoryOrderRequest(BaseModel):
    """POST /api/v1/inventory/unreserve — снятие резерва при отмене заказа."""
    order_id: uuid.UUID
    items: list[InventoryItem] = Field(..., min_length=1)


class InventoryOrderResponse(BaseModel):
    """Ответ на unreserve/fulfill."""
    order_id: str
    status: str
    processed_at: str
