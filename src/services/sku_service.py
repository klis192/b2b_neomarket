"""
Бизнес-логика для SKU.
US-B2B-02: создание SKU.
Побочный эффект: первый SKU → CREATED → ON_MODERATION + событие CREATED в outbox.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models.product import Product, ProductStatus
from src.models.sku import SKU, SKUImage, SKUCharacteristic
from src.models.outbox import Outbox
from src.config import settings
from src.schemas.sku import SKUCreate, SKUResponse


def _sku_to_response(sku: SKU, image_objs=None, char_objs=None) -> SKUResponse:
    """Конвертирует ORM/данные в ответ API — формат SKUResponse из спеки."""
    now = datetime.now(timezone.utc).isoformat()

    # Если объекты переданы — используем их (при создании), иначе из ORM
    if image_objs is not None:
        images = [
            {"id": str(i.id), "url": i.url, "ordering": i.ordering}
            for i in image_objs
        ]
    else:
        images = [
            {"id": str(i.id), "url": i.url, "ordering": i.ordering}
            for i in sorted(sku.images, key=lambda x: x.ordering)
        ]

    if char_objs is not None:
        chars = [
            {"id": str(c.id), "name": c.name, "value": c.value}
            for c in char_objs
        ]
    else:
        chars = [
            {"id": str(c.id), "name": c.name, "value": c.value}
            for c in sku.characteristics
        ]

    return SKUResponse(
        id=str(sku.id),
        product_id=str(sku.product_id),
        name=sku.name,
        price=sku.price,
        discount=sku.discount,
        cost_price=sku.cost_price,
        stock_quantity=sku.stock_quantity,
        active_quantity=sku.active_quantity,
        reserved_quantity=sku.reserved_quantity,
        article=sku.article,
        images=images,
        characteristics=chars,
        created_at=sku.created_at.isoformat() if sku.created_at else now,
        updated_at=sku.updated_at.isoformat() if sku.updated_at else now,
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

    # Считаем существующие SKU (до добавления нового)
    existing_sku_count = db.query(SKU).filter(SKU.product_id == product.id).count()
    is_first_sku = existing_sku_count == 0

    # Создаём SKU
    sku = SKU(
        product_id=product.id,
        name=data.name,
        price=data.price,
        discount=data.discount,
        cost_price=data.cost_price,
        article=data.article,
        stock_quantity=0,     # увеличивается через накладные
        reserved_quantity=0,
    )
    db.add(sku)
    db.flush()

    # Добавляем фото SKU
    image_objs = []
    for img in data.images:
        obj = SKUImage(sku_id=sku.id, url=img.url, ordering=img.ordering)
        db.add(obj)
        image_objs.append(obj)

    # Добавляем характеристики
    char_objs = []
    for char in data.characteristics:
        obj = SKUCharacteristic(sku_id=sku.id, name=char.name, value=char.value)
        db.add(obj)
        char_objs.append(obj)

    # Побочный эффект: первый SKU для CREATED → ON_MODERATION + событие
    if is_first_sku and product.status == ProductStatus.CREATED:
        product.status = ProductStatus.ON_MODERATION

        # Событие CREATED в outbox для Moderation
        db.add(Outbox(
            idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:CREATED"),
            event_type="CREATED",
            payload={
                "product_id": str(product.id),
                "seller_id": str(seller_id),
                "event": "CREATED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
            target_url=f"{settings.moderation_url}/api/v1/events/product",
        ))

    db.commit()

    return _sku_to_response(sku, image_objs=image_objs, char_objs=char_objs)


def update_sku(
    db: Session,
    sku_id: uuid.UUID,
    seller_id: uuid.UUID,
    data: "SKUUpdate",
) -> SKUResponse:
    """
    Редактирование SKU (B2B-3, PATCH).
    Ownership через parent product. HARD_BLOCKED → 403.
    Побочный эффект: MODERATED/BLOCKED → ON_MODERATION + событие EDITED.
    Резервы не затрагиваются.
    """
    from src.schemas.sku import SKUUpdate

    sku = db.query(SKU).filter(SKU.id == sku_id).first()

    if not sku:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    # Ownership через parent product
    product = db.query(Product).filter(Product.id == sku.product_id).first()
    if not product or product.deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "NOT_OWNER", "message": "Product does not belong to the authenticated seller"},
        )

    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"},
        )

    # Обновляем только переданные поля
    if data.name is not None:
        sku.name = data.name
    if data.price is not None:
        sku.price = data.price
    if data.discount is not None:
        sku.discount = data.discount
    if data.cost_price is not None:
        sku.cost_price = data.cost_price
    if data.article is not None:
        sku.article = data.article

    # Характеристики — если переданы, полностью заменяются
    if data.characteristics is not None:
        for char in sku.characteristics:
            db.delete(char)
        db.flush()
        for char in data.characteristics:
            db.add(SKUCharacteristic(
                sku_id=sku.id, name=char.name, value=char.value
            ))

    # Побочный эффект: MODERATED/BLOCKED → ON_MODERATION + событие EDITED
    if product.status in (ProductStatus.MODERATED, ProductStatus.BLOCKED):
        product.status = ProductStatus.ON_MODERATION
        product.blocking_reason_id = None
        product.moderator_comment = None

        db.add(Outbox(
            idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:EDITED:{datetime.now(timezone.utc).isoformat()}"),
            event_type="EDITED",
            payload={
                "product_id": str(product.id),
                "seller_id": str(seller_id),
                "event": "EDITED",
                "date": datetime.now(timezone.utc).isoformat(),
            },
            target_url=f"{settings.moderation_url}/api/v1/events/product",
        ))

    db.commit()

    # Перезагружаем SKU со связями
    sku = db.query(SKU).filter(SKU.id == sku_id).first()
    return _sku_to_response(sku)
