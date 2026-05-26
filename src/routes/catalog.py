"""
Публичный каталог для B2C.
US-B2B-07:
  GET  /api/v1/public/products          — список товаров с фильтрами
  POST /api/v1/public/products/batch    — batch по списку ID
  GET  /api/v1/public/products/{id}     — карточка одного товара
Все требуют X-Service-Key. БЕЗ cost_price и reserved_quantity.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import require_service_key
from src.database import get_db
from src.schemas.catalog import (
    BatchProductsRequest,
    ProductPublicPaginatedResponse,
    ProductPublicResponse,
)
from src.services import catalog_service

router = APIRouter(prefix="/api/v1/public", tags=["Public Catalog"])


@router.get("/products", response_model=ProductPublicPaginatedResponse)
def list_public_products(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category_id: uuid.UUID | None = Query(default=None),
    search: str | None = Query(default=None, min_length=3),
    sort: str = Query(default="created_desc"),
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Каталог товаров для B2C (US-B2B-07).
    Только MODERATED + deleted=false + active_quantity > 0.
    """
    return catalog_service.list_public_products(
        db, limit=limit, offset=offset,
        category_id=category_id, search=search, sort=sort,
    )


@router.post("/products/batch", response_model=list[ProductPublicResponse])
def batch_public_products(
    data: BatchProductsRequest,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Batch-запрос товаров по списку ID (для подборок/избранного B2C).
    Отсутствующие/невидимые — просто не в ответе (не 404).
    """
    return catalog_service.batch_public_products(db, data.product_ids)


@router.get("/products/{product_id}", response_model=ProductPublicResponse)
def get_public_product(
    product_id: uuid.UUID,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Карточка товара для витрины B2C.
    Условия видимости применяются — невидимый → 404.
    """
    return catalog_service.get_public_product(db, product_id)
