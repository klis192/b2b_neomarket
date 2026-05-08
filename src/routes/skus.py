"""
Эндпоинты SKU.
US-B2B-02: POST /api/v1/skus — создание варианта товара.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller
from src.database import get_db
from src.schemas.sku import SKUCreate, SKUResponse
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
