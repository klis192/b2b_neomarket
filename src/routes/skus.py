"""
Эндпоинты SKU.
US-B2B-02: POST /api/v1/skus — создание.
US-B2B-03: PATCH /api/v1/skus/{id} — редактирование.
US-B2B-12: DELETE /api/v1/skus/{id} — удаление.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller
from src.database import get_db
from src.schemas.sku import SKUCreate, SKUResponse, SKUUpdate
from src.services import sku_service

router = APIRouter(prefix="/api/v1/skus", tags=["SKU"])


@router.post("", response_model=SKUResponse, status_code=201)
def create_sku(
    data: SKUCreate,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Создание SKU (US-B2B-02).
    Побочный эффект: первый SKU → товар переходит в ON_MODERATION.
    """
    return sku_service.create_sku(db, seller_id, data)


@router.patch("/{sku_id}", response_model=SKUResponse)
def update_sku(
    sku_id: uuid.UUID,
    data: SKUUpdate,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Редактирование SKU (US-B2B-03, PATCH).
    Ownership через parent product.
    MODERATED/BLOCKED → ON_MODERATION + событие EDITED.
    """
    return sku_service.update_sku(db, sku_id, seller_id, data)


@router.delete("/{sku_id}", status_code=204)
def delete_sku(
    sku_id: uuid.UUID,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Удаление SKU (US-B2B-12).
    HARD_BLOCKED → 403. reserved_quantity > 0 → 409.
    Последний SKU + ON_MODERATION → CREATED + событие DELETED.
    """
    sku_service.delete_sku(db, sku_id, seller_id)
    return None
