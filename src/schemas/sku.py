"""
Pydantic-схемы для SKU.
Формат запроса/ответа — по спеке b2b-flows B2B-2.
"""

import uuid

from pydantic import BaseModel, Field


class SKUCharacteristicSchema(BaseModel):
    """Характеристика SKU (название + значение)."""
    name: str
    value: str

    model_config = {"from_attributes": True}


class SKUCreate(BaseModel):
    """
    Создание SKU (POST /api/v1/skus).
    price и cost_price — в копейках, > 0.
    image — обязательное, одиночная ссылка на фото.
    discount — абсолютная скидка в копейках, по умолчанию 0.
    """
    product_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    price: int = Field(..., gt=0, description="Цена продажи в копейках")
    cost_price: int = Field(..., gt=0, description="Себестоимость в копейках")
    discount: int = Field(default=0, ge=0, description="Скидка в копейках")
    image: str = Field(..., min_length=1, description="URL фото SKU")
    characteristics: list["SKUCharacteristicCreate"] = Field(default_factory=list)


class SKUCharacteristicCreate(BaseModel):
    """Характеристика при создании SKU."""
    name: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)


class SKUResponse(BaseModel):
    """Ответ с SKU — формат из спеки."""
    id: str
    product_id: str
    name: str
    price: int
    cost_price: int
    discount: int
    image: str | None
    active_quantity: int
    reserved_quantity: int
    characteristics: list[SKUCharacteristicSchema]

    model_config = {"from_attributes": True}
