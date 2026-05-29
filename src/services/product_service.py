"""
Бизнес-логика для товаров.
US-B2B-01: создание карточки товара.
US-B2B-05 (базовый): получение товара по ID.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, subqueryload

from src.models.category import Category
from src.models.product import (
    Product,
    ProductCharacteristic,
    ProductImage,
    ProductStatus,
)
from src.models.sku import SKU
from src.models.outbox import Outbox
from src.config import settings
from src.schemas.product import ProductCreate, ProductResponse


def _product_to_response(product: Product) -> ProductResponse:
    """Конвертирует ORM-объект в ответ API — формат ProductResponse из спеки + канон."""
    return ProductResponse(
        id=str(product.id),
        seller_id=str(product.seller_id),
        category_id=str(product.category_id),
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status.value,
        deleted=product.deleted,
        # blocked — простой флаг для UI (канон B2B-5)
        blocked=product.status in (ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED),
        blocking_reason_id=str(product.blocking_reason_id) if product.blocking_reason_id else None,
        moderator_comment=product.moderator_comment,
        # Полный объект причины блокировки {id, title, comment} — канон B2B-5
        blocking_reason=product.blocking_reason,
        # Замечания по полям [{field_name, sku_id, comment}] — канон B2B-5
        field_reports=product.field_reports or [],
        images=[
            {"id": str(img.id), "url": img.url, "ordering": img.ordering}
            for img in sorted(product.images, key=lambda x: x.ordering)
        ],
        characteristics=[
            {"id": str(c.id), "name": c.name, "value": c.value}
            for c in product.characteristics
        ],
        skus=[
            {
                "id": str(sku.id),
                "name": sku.name,
                "price": sku.price,
                "discount": sku.discount,
                "cost_price": sku.cost_price,
                "stock_quantity": sku.stock_quantity,
                "active_quantity": sku.active_quantity,
                "reserved_quantity": sku.reserved_quantity,
                "article": sku.article,
                "images": [
                    {"id": str(si.id), "url": si.url, "ordering": si.ordering}
                    for si in sorted(sku.images, key=lambda x: x.ordering)
                ],
                "characteristics": [
                    {"id": str(c.id), "name": c.name, "value": c.value}
                    for c in sku.characteristics
                ],
                "created_at": sku.created_at.isoformat() if sku.created_at else "",
                "updated_at": sku.updated_at.isoformat() if sku.updated_at else "",
            }
            for sku in product.skus
        ],
        created_at=product.created_at.isoformat() if product.created_at else "",
        updated_at=product.updated_at.isoformat() if product.updated_at else "",
    )


def _load_product(db: Session, product_id: uuid.UUID) -> Product | None:
    """Загружает товар со всеми связями одним запросом."""
    return (
        db.query(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.images),
            joinedload(Product.characteristics),
            joinedload(Product.skus).subqueryload(SKU.characteristics),
            joinedload(Product.skus).subqueryload(SKU.images),
        )
        .filter(Product.id == product_id)
        .first()
    )


def get_product_by_id(
    db: Session,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> ProductResponse:
    """
    Получить товар по ID (для seller-а).
    Чужой товар → 404 (не раскрываем существование).
    """
    product = _load_product(db, product_id)

    if not product or product.seller_id != seller_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    return _product_to_response(product)


def create_product(
    db: Session,
    seller_id: uuid.UUID,
    data: ProductCreate,
) -> ProductResponse:
    """
    Создание товара (B2B-1).
    seller_id из JWT — защита от IDOR.
    Статус = CREATED, на модерацию не отправляется (нужен хотя бы один SKU).
    """
    # Проверяем что категория существует
    category = db.query(Category).filter(Category.id == data.category_id).first()
    if not category:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Category not found"},
        )

    # Создаём товар
    product = Product(
        seller_id=seller_id,
        title=data.title,
        slug=data.slug,
        description=data.description,
        category_id=data.category_id,
        status=ProductStatus.CREATED,
    )
    db.add(product)
    db.flush()

    # Добавляем фото
    image_objs = []
    for img in data.images:
        obj = ProductImage(product_id=product.id, url=img.url, ordering=img.ordering)
        db.add(obj)
        image_objs.append(obj)

    # Добавляем характеристики
    char_objs = []
    for char in data.characteristics:
        obj = ProductCharacteristic(product_id=product.id, name=char.name, value=char.value)
        db.add(obj)
        char_objs.append(obj)

    db.commit()

    # Формируем ответ из данных в памяти (обходим SQLite UUID баг)
    now = datetime.now(timezone.utc).isoformat()
    return ProductResponse(
        id=str(product.id),
        seller_id=str(seller_id),
        category_id=str(data.category_id),
        title=data.title,
        slug=data.slug,
        description=data.description,
        status=ProductStatus.CREATED.value,
        deleted=False,
        blocked=False,
        blocking_reason_id=None,
        moderator_comment=None,
        blocking_reason=None,
        field_reports=[],
        images=[
            {"id": str(img.id), "url": img.url, "ordering": img.ordering}
            for img in image_objs
        ],
        characteristics=[
            {"id": str(c.id), "name": c.name, "value": c.value}
            for c in char_objs
        ],
        skus=[],
        created_at=now,
        updated_at=now,
    )


def update_product(
    db: Session,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
    data: "ProductUpdate",
) -> ProductResponse:
    """
    Редактирование товара (B2B-3, PATCH).
    HARD_BLOCKED → 403. Чужой товар → 403 NOT_OWNER.
    Побочный эффект: MODERATED/BLOCKED → ON_MODERATION + событие EDITED.
    """
    from src.schemas.product import ProductUpdate

    product = db.query(Product).filter(Product.id == product_id).first()

    # Не найден
    if not product or product.deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    # Чужой товар — 403 (продавец знает что товар существует, он его создал)
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "NOT_OWNER", "message": "Product does not belong to the authenticated seller"},
        )

    # HARD_BLOCKED — нельзя редактировать
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"},
        )

    # Обновляем только переданные поля (семантика PATCH)
    if data.title is not None:
        product.title = data.title
    if data.description is not None:
        product.description = data.description
    if data.category_id is not None:
        category = db.query(Category).filter(Category.id == data.category_id).first()
        if not category:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "Category not found"},
            )
        product.category_id = data.category_id

    # Характеристики — если переданы, полностью заменяются
    if data.characteristics is not None:
        for char in product.characteristics:
            db.delete(char)
        db.flush()
        for char in data.characteristics:
            db.add(ProductCharacteristic(
                product_id=product.id, name=char.name, value=char.value
            ))

    # Побочный эффект: MODERATED/BLOCKED → ON_MODERATION + событие EDITED
    if product.status in (ProductStatus.MODERATED, ProductStatus.BLOCKED):
        # Запоминаем updated_at ДО изменения — для стабильного idempotency_key при retry
        version_ts = product.updated_at.isoformat() if product.updated_at else "init"
        product.status = ProductStatus.ON_MODERATION
        # Очищаем данные блокировки (товар исправлен)
        product.blocking_reason_id = None
        product.moderator_comment = None
        product.blocking_reason = None
        product.field_reports = None

        idem_key = uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:EDITED:{version_ts}")
        db.add(Outbox(
            idempotency_key=idem_key,
            event_type="EDITED",
            payload={
                "event_type": "EDITED",
                "idempotency_key": str(idem_key),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "product_id": str(product.id),
                    "seller_id": str(seller_id),
                },
            },
            target_url=f"{settings.moderation_url}/api/v1/events/product",
        ))

    db.commit()

    # Перезагружаем со связями
    loaded = _load_product(db, product_id)
    return _product_to_response(loaded)


def delete_product(
    db: Session,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> None:
    """
    Мягкое удаление товара (B2B-4).
    deleted = True. Товар не удаляется физически.
    Побочные эффекты: событие DELETED → Moderation, PRODUCT_DELETED → B2C.
    """
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "NOT_OWNER", "message": "Product does not belong to the authenticated seller"},
        )

    # Уже удалён
    if product.deleted:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Product already deleted"},
        )

    # HARD_BLOCKED — нельзя удалять
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Cannot delete hard-blocked product"},
        )

    # Soft delete
    product.deleted = True

    # Собираем sku_ids для события B2C
    sku_ids = [str(sku.id) for sku in product.skus]
    now = datetime.now(timezone.utc).isoformat()

    # Событие PRODUCT_DELETED → Moderation (обёртка с вложенным payload)
    db.add(Outbox(
        idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:PRODUCT_DELETED:MOD"),
        event_type="PRODUCT_DELETED",
        payload={
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:PRODUCT_DELETED:MOD")),
            "occurred_at": now,
            "payload": {
                "product_id": str(product.id),
                "seller_id": str(seller_id),
            },
        },
        target_url=f"{settings.moderation_url}/api/v1/events/product",
    ))

    # Событие PRODUCT_DELETED → B2C (обёртка с вложенным payload)
    db.add(Outbox(
        idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:PRODUCT_DELETED:B2C"),
        event_type="PRODUCT_DELETED",
        payload={
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:PRODUCT_DELETED:B2C")),
            "occurred_at": now,
            "payload": {
                "product_id": str(product.id),
                "sku_ids": sku_ids,
            },
        },
        target_url=f"{settings.b2c_url}/api/v1/events/product",
    ))

    db.commit()


def get_product_by_id_service(
    db: Session,
    product_id: uuid.UUID,
) -> ProductResponse:
    """
    Получить товар по ID (service mode — Moderation/B2C через X-Service-Key).
    Ownership НЕ проверяется — Moderation видит товары всех продавцов.
    """
    product = _load_product(db, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    return _product_to_response(product)


def list_seller_products(
    db: Session,
    seller_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    include_deleted: bool = False,
) -> dict:
    """
    Список товаров продавца (B2B-11).
    Автоматический фильтр по seller_id из JWT — IDOR невозможен.
    Видны все статусы. Deleted видны только с include_deleted=true.
    """
    from sqlalchemy import func

    query = db.query(Product).options(
        joinedload(Product.images),
        joinedload(Product.skus),
    ).filter(Product.seller_id == seller_id)

    # Фильтр по статусу
    if status:
        query = query.filter(Product.status == status)

    # По умолчанию скрываем удалённые
    if not include_deleted:
        query = query.filter(Product.deleted == False)  # noqa: E712

    # Считаем total
    count_q = db.query(func.count(Product.id)).filter(Product.seller_id == seller_id)
    if status:
        count_q = count_q.filter(Product.status == status)
    if not include_deleted:
        count_q = count_q.filter(Product.deleted == False)  # noqa: E712
    total_count = count_q.scalar()

    products = query.order_by(Product.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for p in products:
        # min_price — минимальная цена среди SKU
        prices = [sku.price - sku.discount for sku in p.skus if sku.active_quantity > 0]
        min_price = min(prices) if prices else None

        # cover_image — первое фото
        cover = None
        if p.images:
            sorted_imgs = sorted(p.images, key=lambda x: x.ordering)
            cover = sorted_imgs[0].url

        items.append({
            "id": str(p.id),
            "title": p.title,
            "slug": p.slug,
            "status": p.status.value,
            "category_id": str(p.category_id),
            "deleted": p.deleted,
            "created_at": p.created_at.isoformat() if p.created_at else "",
            "min_price": min_price,
            "cover_image": cover,
        })

    return {
        "items": items,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
    }
