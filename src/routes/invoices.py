"""
Эндпоинты для накладных.
US-B2B-06:
  POST /api/v1/invoices          — создание накладной
  POST /api/v1/invoices/{id}/accept — приёмка (Django Admin / оператор)
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller
from src.database import get_db
from src.schemas.invoice import InvoiceAcceptRequest, InvoiceCreate, InvoiceResponse
from src.services import invoice_service

router = APIRouter(prefix="/api/v1/invoices", tags=["Invoices"])


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
    db: Session = Depends(get_db),
):
    """
    Приёмка накладной (US-B2B-06, Django Admin / оператор).
    Пустое тело → полная приёмка. accepted_items → частичная.
    Атомарно обновляет stock_quantity.
    """
    return invoice_service.accept_invoice(db, invoice_id, data)
