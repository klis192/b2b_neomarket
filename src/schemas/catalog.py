"""
Pydantic-схемы для публичного каталога (B2C).
БЕЗ cost_price и reserved_quantity — коммерчески-чувствительные поля только для seller.
"""

import uuid

from pydantic import BaseModel, Field


# --- SKU для витрины (без cost_price, reserved_quantity) ---

class SKUPublicResponse(BaseModel):
    """SKU для B2C — без себестоимости и резервов."""
    id: str
    product_id: str
    name: str
    price: int
    discount: int
    stock_quantity: int
    active_quantity: int
    article: str | None
    images: list[dict]       # [{id, url, ordering}]
    characteristics: list[dict]  # [{id, name, value}]


# --- Полная карточка для витрины ---

class ProductPublicResponse(BaseModel):
    """Полная карточка товара для B2C — ProductPublicResponse из протокола."""
    id: str
    seller_id: str
    category_id: str
    title: str
    slug: str | None
    description: str
    status: str
    images: list[dict]           # [{id, url, ordering}]
    characteristics: list[dict]  # [{id, name, value}]
    skus: list[SKUPublicResponse]
    created_at: str
    updated_at: str


# --- Краткая карточка для списка ---

class ProductPublicShortResponse(BaseModel):
    """Краткая карточка для пагинированного списка."""
    id: str
    title: str
    slug: str | None
    status: str
    category_id: str
    min_price: int | None  # минимальная цена среди SKU
    cover_image: str | None  # первое фото товара
    created_at: str


class ProductPublicPaginatedResponse(BaseModel):
    """Пагинированный список товаров для витрины."""
    items: list[ProductPublicShortResponse]
    total_count: int
    limit: int
    offset: int


# --- Batch request ---

class BatchProductsRequest(BaseModel):
    """POST /api/v1/public/products/batch — запрос по списку ID."""
    product_ids: list[uuid.UUID] = Field(..., max_length=100)
