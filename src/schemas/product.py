"""
Pydantic-схемы для товаров.
Формат запроса/ответа — по спеке b2b-flows B2B-1.
"""

import uuid

from pydantic import BaseModel, Field


# --- Вложенные объекты ---

class ImageSchema(BaseModel):
    """Фото товара в ответе."""
    url: str
    ordering: int

    model_config = {"from_attributes": True}


class CharacteristicSchema(BaseModel):
    """Характеристика товара (название + значение)."""
    name: str
    value: str

    model_config = {"from_attributes": True}


class CategoryRef(BaseModel):
    """Краткая ссылка на категорию в ответе."""
    id: str
    name: str

    model_config = {"from_attributes": True}


# --- Запрос на создание ---

class ImageCreate(BaseModel):
    """Фото при создании товара."""
    url: str = Field(..., min_length=1)
    ordering: int = Field(..., ge=0)


class CharacteristicCreate(BaseModel):
    """Характеристика при создании товара."""
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class ProductCreate(BaseModel):
    """
    Создание товара (POST /api/v1/products).
    title и description обязательны.
    images — минимум 1 фото.
    characteristics — опционально.
    """
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=5000)
    category_id: uuid.UUID
    images: list[ImageCreate] = Field(..., min_length=1)
    characteristics: list[CharacteristicCreate] = Field(default_factory=list)


# --- Ответ ---

class ProductResponse(BaseModel):
    """
    Полный ответ с товаром — формат из спеки.
    blocked вычисляется из status (BLOCKED или HARD_BLOCKED).
    skus — пустой массив при создании.
    """
    id: str
    title: str
    description: str
    status: str
    deleted: bool
    blocked: bool
    category: CategoryRef
    images: list[ImageSchema]
    characteristics: list[CharacteristicSchema]
    skus: list = Field(default_factory=list)

    model_config = {"from_attributes": True}
