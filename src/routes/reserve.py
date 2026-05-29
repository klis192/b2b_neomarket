"""
Эндпоинты резервирования и списания.
US-B2B-08:
  POST /api/v1/inventory/reserve   — all-or-nothing резервирование
  POST /api/v1/inventory/unreserve — снятие резерва при отмене заказа
US-B2B-10:
  POST /api/v1/inventory/fulfill   — списание при доставке
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import require_service_key
from src.database import get_db
from src.schemas.reserve import (
    InventoryOrderRequest,
    InventoryOrderResponse,
    ReserveRequest,
    ReserveResponse,
)
from src.services import reserve_service

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])


@router.post("/reserve", response_model=ReserveResponse)
def reserve(
    data: ReserveRequest,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    All-or-nothing резервирование SKU (US-B2B-08).
    Идемпотентно по idempotency_key. X-Service-Key обязателен.
    """
    return reserve_service.reserve_skus(db, data)


@router.post("/unreserve", response_model=InventoryOrderResponse)
def unreserve(
    data: InventoryOrderRequest,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Снятие резерва при отмене заказа (US-B2B-08).
    X-Service-Key обязателен.
    """
    return reserve_service.unreserve_skus(db, data)


@router.post("/fulfill", response_model=InventoryOrderResponse)
def fulfill(
    data: InventoryOrderRequest,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Списание при доставке (US-B2B-10).
    reserved_quantity -= N, stock_quantity -= N.
    Идемпотентно по order_id. X-Service-Key обязателен.
    """
    return reserve_service.fulfill_order(db, data)
