"""
Бизнес-логика для SKU.
US-B2B-02: создание SKU.
Побочный эффект: первый SKU → CREATED → ON_MODERATION + событие в Moderation.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models.product import Product, ProductStatus
from src.models.sku import SKU, SKUCharacteristic
from src.models.outbox import Outbox
from src.config import settings
from src.schemas.sku import SKUCreate, SKUResponse


def _sku_to_response(sku: SKU) -> SKUResponse:
    """Конвертирует ORM-объект SKU в ответ API."""
    return SKUResponse(
        id=str(sku.id),
        product_id=str(sku.product_id),
        name=sku.name,
        price=sku.price,
        cost_price=sku.cost_price,
        discount=sku.discount,
        image=sku.image,
        active_quantity=sku.active_quantity,
        reserved_quantity=sku.reserved_quantity,
        characteristics=[
            {"name": c.name, "value": c.value}
            for c in sku.characteristics
        ],
    )


def create_sku(
    db: Session,
    seller_id: uuid.UUID,
    data: SKUCreate,
) -> SKUResponse:
    """
    Создание SKU (B2B-2).
    Проверяет ownership товара и статус.
    Побочный эффект: первый SKU для CREATED товара → ON_MODERATION.
    """
    # Ищем товар — если не найден или чужой → 404 (не раскрываем существование)
    product = db.query(Product).filter(
        Product.id == data.product_id,
        Product.seller_id == seller_id,
        Product.deleted == False,  # noqa: E712
    ).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    # HARD_BLOCKED — нельзя добавлять SKU
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Cannot add SKU to hard-blocked product"},
        )

    # Проверяем, есть ли уже SKU у товара (до добавления нового)
    existing_sku_count = db.query(SKU).filter(SKU.product_id == product.id).count()
    is_first_sku = existing_sku_count == 0

    # Создаём SKU
    sku = SKU(
        product_id=product.id,
        name=data.name,
        price=data.price,
        cost_price=data.cost_price,
        discount=data.discount,
        image=data.image,
        active_quantity=0,  # увеличивается только через накладные
        reserved_quantity=0,
    )
    db.add(sku)
    db.flush()

    # Добавляем характеристики
    for char in data.characteristics:
        db.add(SKUCharacteristic(
            sku_id=sku.id,
            name=char.name,
            value=char.value,
        ))

    # Побочный эффект: первый SKU для CREATED товара → ON_MODERATION
    if is_first_sku and product.status == ProductStatus.CREATED:
        product.status = ProductStatus.ON_MODERATION

        # Записываем событие в outbox (fire-and-forget на M1)
        event = Outbox(
            idempotency_key=uuid.uuid4(),
            event_type="CREATED",
            payload={
                "product_id": str(product.id),
                "seller_id": str(seller_id),
                "event": "CREATED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
            target_url=f"{settings.moderation_url}/api/v1/events/product",
        )
        db.add(event)

    db.commit()

    # Формируем ответ из данных в памяти
    return SKUResponse(
        id=str(sku.id),
        product_id=str(data.product_id),
        name=data.name,
        price=data.price,
        cost_price=data.cost_price,
        discount=data.discount,
        image=data.image,
        active_quantity=0,
        reserved_quantity=0,
        characteristics=[
            {"name": c.name, "value": c.value}
            for c in data.characteristics
        ],
    )
