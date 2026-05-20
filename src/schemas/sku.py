"""
Pydantic-схемы для SKU.
Формат по спеке neomarket-protocols/b2b/openapi.yaml.
"""

import uuid

from pydantic import BaseModel, Field


# --- Вложенные объекты ---

class SKUImageCreate(BaseModel):
    """Фото при создании SKU."""
    url: str = Field(..., min_length=1)
    ordering: int = Field(default=0, ge=0)

class SKUCharacteristicCreate(BaseModel):
    """Характеристика при создании SKU."""
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)

class SKUImageResponse(BaseModel):
    """Фото SKU в ответе (с id)."""
    id: str
    url: str
    ordering: int

class SKUCharacteristicResponse(BaseModel):
    """Характеристика SKU в ответе (с id)."""
    id: str
    name: str
    value: str


# --- Запрос ---

class SKUCreate(BaseModel):
    """
    POST /api/v1/skus — создание SKU.
    Required: product_id, name, price.
    cost_price — nullable (по спеке).
    article — nullable.
    images — default [] (массив, не одиночная строка).
    """
    product_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    price: int = Field(..., ge=0, description="Цена в копейках")
    discount: int = Field(default=0, ge=0, description="Скидка в копейках")
    cost_price: int | None = Field(default=None, description="Себестоимость в копейках, nullable")
    article: str | None = Field(default=None, description="Артикул")
    images: list[SKUImageCreate] = Field(default_factory=list)
    characteristics: list[SKUCharacteristicCreate] = Field(default_factory=list)


# --- Ответ ---

class SKUResponse(BaseModel):
    """
    Seller-view SKU — SKUResponse из спеки.
    Все обязательные поля: id, product_id, name, price, discount,
    cost_price, stock_quantity, active_quantity, reserved_quantity,
    article, images, characteristics, created_at, updated_at.
    """
    id: str
    product_id: str
    name: str
    price: int
    discount: int
    cost_price: int | None
    stock_quantity: int
    active_quantity: int
    reserved_quantity: int
    article: str | None
    images: list[SKUImageResponse]
    characteristics: list[SKUCharacteristicResponse]
    created_at: str
    updated_at: str
