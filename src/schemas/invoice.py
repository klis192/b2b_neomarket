"""
Pydantic-схемы для накладных.
Формат по протоколу neomarket-protocols/b2b/openapi.yaml.
"""

import uuid

from pydantic import BaseModel, Field


# --- Создание ---

class InvoiceItemCreate(BaseModel):
    """Позиция накладной при создании."""
    sku_id: uuid.UUID
    quantity: int = Field(..., ge=1, description="Заявленное количество, > 0")


class InvoiceCreate(BaseModel):
    """POST /api/v1/invoices — создание накладной."""
    items: list[InvoiceItemCreate] = Field(..., min_length=1)


# --- Приёмка ---

class AcceptItem(BaseModel):
    """Одна позиция при приёмке — сколько фактически принято."""
    invoice_item_id: uuid.UUID
    accepted_quantity: int = Field(..., ge=0)


class InvoiceAcceptRequest(BaseModel):
    """
    POST /api/v1/invoices/{id}/accept — приёмка.
    Если accepted_items не передан — полная приёмка (все quantity = accepted).
    """
    accepted_items: list[AcceptItem] | None = None


# --- Ответ ---

class InvoiceItemResponse(BaseModel):
    """Позиция накладной в ответе."""
    id: str
    sku_id: str
    quantity: int
    accepted_quantity: int | None


class InvoiceResponse(BaseModel):
    """
    InvoiceResponse по протоколу.
    Required: id, seller_id, status, items, created_at, updated_at.
    """
    id: str
    seller_id: str
    status: str
    items: list[InvoiceItemResponse]
    created_at: str
    updated_at: str
    accepted_at: str | None = None
    accepted_by: str | None = None


class InvoicePaginatedResponse(BaseModel):
    """Список накладных с пагинацией."""
    items: list[InvoiceResponse]
    total_count: int
    limit: int
    offset: int
