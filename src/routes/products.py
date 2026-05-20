"""
Эндпоинты товаров.
US-B2B-01: POST /api/v1/products — создание карточки товара.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller
from src.database import get_db
from src.schemas.product import ProductCreate, ProductResponse, ProductUpdate
from src.services import product_service

router = APIRouter(prefix="/api/v1/products", tags=["Products"])


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    data: ProductCreate,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Создание товара (US-B2B-01).
    seller_id берётся из JWT — никогда из тела запроса.
    Статус = CREATED. На модерацию не отправляется.
    """
    return product_service.create_product(db, seller_id, data)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: uuid.UUID,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Получить товар по ID (US-B2B-05, базовый).
    Только свои товары — чужие → 404.
    """
    return product_service.get_product_by_id(db, product_id, seller_id)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Редактирование товара (US-B2B-03, PATCH).
    MODERATED/BLOCKED → ON_MODERATION + событие EDITED.
    HARD_BLOCKED → 403.
    """
    return product_service.update_product(db, product_id, seller_id, data)
