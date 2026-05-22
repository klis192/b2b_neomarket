"""
Эндпоинты товаров.
US-B2B-01: POST /api/v1/products — создание карточки товара.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_seller, get_optional_seller, require_service_key
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
    """
    return product_service.create_product(db, seller_id, data)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: uuid.UUID,
    authorization: str | None = Header(default=None),
    x_service_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Просмотр товара (US-B2B-05). Два режима:
    1. Bearer JWT (seller) — видит только свои товары, чужие → 404.
    2. X-Service-Key (Moderation/B2C) — видит любые товары, ownership не проверяется.
    """
    seller_id = None
    service = None

    # Пробуем JWT
    if authorization and authorization.startswith("Bearer "):
        seller_id = get_current_seller(authorization)

    # Пробуем X-Service-Key
    if x_service_key:
        try:
            service = require_service_key(x_service_key)
        except HTTPException:
            pass

    # Ни одного способа авторизации
    if seller_id is None and service is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Требуется Bearer токен или X-Service-Key"},
        )

    # Service mode — видит любые товары
    if service:
        return product_service.get_product_by_id_service(db, product_id)

    # Seller mode — только свои
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


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: uuid.UUID,
    seller_id: uuid.UUID = Depends(get_current_seller),
    db: Session = Depends(get_db),
):
    """
    Мягкое удаление товара (US-B2B-04).
    deleted=true. Событие DELETED → Moderation, PRODUCT_DELETED → B2C.
    """
    product_service.delete_product(db, product_id, seller_id)
    return None
