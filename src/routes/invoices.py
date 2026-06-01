"""
Эндпоинты для накладных.
US-B2B-06:
  GET  /api/v1/invoices              — список накладных продавца
  POST /api/v1/invoices              — создание накладной
  POST /api/v1/invoices/{id}/accept  — приёмка
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller
from src.database import get_db
from src.schemas.invoice import (
    InvoiceAcceptRequest,
    InvoiceCreate,
    InvoicePaginatedResponse,
    InvoiceResponse,
)
from src.services import invoice_service

router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])


@router.get("", response_model=InvoicePaginatedResponse)
def list_invoices(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Список накладных продавца (US-B2B-06).
    Только свои — seller_id из JWT.
    """
    return invoice_service.list_invoices(db, seller_id, limit, offset, status)


@router.post("", response_model=InvoiceResponse, status_code=201)
def create_invoice(
    data: InvoiceCreate,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Создание накладной (US-B2B-06).
    Все SKU должны принадлежать seller из JWT.
    Товар каждого SKU должен быть MODERATED.
    """
    return invoice_service.create_invoice(db, seller_id, data)


@router.post("/{invoice_id}/accept", response_model=InvoiceResponse)
def accept_invoice(
    invoice_id: uuid.UUID,
    data: InvoiceAcceptRequest | None = None,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Приёмка накладной (US-B2B-06).
    Проверяет ownership — только владелец накладной может принять.
    Фиксирует актора в accepted_by.
    """
    return invoice_service.accept_invoice(db, invoice_id, seller_id, data)
