"""
Pydantic-схемы для товаров.
Формат по спеке neomarket-protocols/b2b/openapi.yaml.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Вложенные объекты для ответа (с id по спеке) ---

class ProductImageResponse(BaseModel):
    """Фото товара в ответе — ProductImageResponse из спеки."""
    id: str
    url: str
    ordering: int

class CharacteristicResponse(BaseModel):
    """Характеристика в ответе — CharacteristicResponse из спеки (с id)."""
    id: str
    name: str
    value: str

class SKUImageResponse(BaseModel):
    """Фото SKU в ответе."""
    id: str
    url: str
    ordering: int

class SKUShortResponse(BaseModel):
    """Краткий SKU внутри ProductResponse."""
    id: str
    name: str
    price: int
    discount: int
    cost_price: int | None
    stock_quantity: int
    active_quantity: int
    reserved_quantity: int
    article: str | None
    images: list[SKUImageResponse]
    characteristics: list[CharacteristicResponse]
    created_at: str
    updated_at: str


# --- Запрос на создание ---

class ProductImageCreate(BaseModel):
    """Фото при создании товара."""
    url: str = Field(..., min_length=1)
    ordering: int = Field(default=0, ge=0)

class CharacteristicCreate(BaseModel):
    """Характеристика при создании товара."""
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)

class ProductCreate(BaseModel):
    """
    POST /api/v1/products — создание товара.
    Required: title, description, category_id.
    images — default [] (необязательно по спеке).
    slug — nullable (необязательно).
    """
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=5000)
    category_id: uuid.UUID
    slug: str | None = None
    images: list[ProductImageCreate] = Field(..., min_length=1)
    characteristics: list[CharacteristicCreate] = Field(default_factory=list)


# --- Ответ ---

class ProductResponse(BaseModel):
    """
    Полный seller-view ответ — ProductResponse из спеки + канон-поля.
    Обязательные по openapi: id, seller_id, category_id, title, slug,
    description, status, deleted, blocking_reason_id, moderator_comment,
    images, characteristics, skus, created_at, updated_at.
    Канон-расширения: blocked, blocking_reason, field_reports.
    """
    id: str
    seller_id: str
    category_id: str
    title: str
    slug: str | None
    description: str
    status: str
    deleted: bool
    blocked: bool  # вычисляется из status (BLOCKED или HARD_BLOCKED)
    blocking_reason_id: str | None
    moderator_comment: str | None
    # Полный объект причины блокировки {id, title, comment} — канон B2B-5
    blocking_reason: dict | None = None
    # Замечания по полям [{field_name, sku_id, comment}] — канон B2B-5
    field_reports: list = Field(default_factory=list)
    images: list[ProductImageResponse]
    characteristics: list[CharacteristicResponse]
    skus: list[SKUShortResponse]
    created_at: str
    updated_at: str


# --- Запрос на обновление (PATCH — все поля опциональны) ---

class ProductUpdate(BaseModel):
    """
    PATCH /api/v1/products/{id} — редактирование товара.
    Семантика PATCH — обновляются только переданные поля.
    Если characteristics переданы — заменяются полностью.
    """
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category_id: uuid.UUID | None = None
    characteristics: list[CharacteristicCreate] | None = None
