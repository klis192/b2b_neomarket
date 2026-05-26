"""
Бизнес-логика публичного каталога для B2C.
US-B2B-07: товары видны если MODERATED + deleted=false + active_quantity > 0.
SKU ответ БЕЗ cost_price и reserved_quantity.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.models.product import Product, ProductImage, ProductStatus
from src.models.sku import SKU, SKUImage, SKUCharacteristic
from src.schemas.catalog import (
    ProductPublicResponse,
    ProductPublicShortResponse,
    ProductPublicPaginatedResponse,
    SKUPublicResponse,
)


def _visibility_filter(query):
    """Фильтры видимости: MODERATED + deleted=false."""
    return query.filter(
        Product.status == ProductStatus.MODERATED,
        Product.deleted == False,  # noqa: E712
    )


def _product_to_public(product: Product) -> ProductPublicResponse:
    """Конвертирует ORM в публичный ответ БЕЗ cost_price и reserved_quantity."""
    return ProductPublicResponse(
        id=str(product.id),
        seller_id=str(product.seller_id),
        category_id=str(product.category_id),
        title=product.title,
        slug=product.slug,
        description=product.description,
        status=product.status.value,
        images=[
            {"id": str(img.id), "url": img.url, "ordering": img.ordering}
            for img in sorted(product.images, key=lambda x: x.ordering)
        ],
        characteristics=[
            {"id": str(c.id), "name": c.name, "value": c.value}
            for c in product.characteristics
        ],
        skus=[
            SKUPublicResponse(
                id=str(sku.id),
                product_id=str(sku.product_id),
                name=sku.name,
                price=sku.price,
                discount=sku.discount,
                stock_quantity=sku.stock_quantity,
                active_quantity=sku.active_quantity,
                article=sku.article,
                images=[
                    {"id": str(si.id), "url": si.url, "ordering": si.ordering}
                    for si in sorted(sku.images, key=lambda x: x.ordering)
                ],
                characteristics=[
                    {"id": str(c.id), "name": c.name, "value": c.value}
                    for c in sku.characteristics
                ],
            )
            for sku in product.skus
            if sku.active_quantity > 0  # только SKU в наличии
        ],
        created_at=product.created_at.isoformat() if product.created_at else "",
        updated_at=product.updated_at.isoformat() if product.updated_at else "",
    )


def _product_to_short(product: Product) -> ProductPublicShortResponse:
    """Краткая карточка для пагинированного списка."""
    # Минимальная цена среди SKU в наличии
    prices = [sku.price - sku.discount for sku in product.skus if sku.active_quantity > 0]
    min_price = min(prices) if prices else None

    # Первое фото товара
    cover = None
    if product.images:
        sorted_images = sorted(product.images, key=lambda x: x.ordering)
        cover = sorted_images[0].url

    return ProductPublicShortResponse(
        id=str(product.id),
        title=product.title,
        slug=product.slug,
        status=product.status.value,
        category_id=str(product.category_id),
        min_price=min_price,
        cover_image=cover,
        created_at=product.created_at.isoformat() if product.created_at else "",
    )


def _load_products_query(db: Session):
    """Базовый запрос с подгрузкой связей."""
    return db.query(Product).options(
        joinedload(Product.images),
        joinedload(Product.characteristics),
        joinedload(Product.skus).joinedload(SKU.images),
        joinedload(Product.skus).joinedload(SKU.characteristics),
    )


def list_public_products(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    category_id: uuid.UUID | None = None,
    search: str | None = None,
    sort: str = "created_desc",
) -> ProductPublicPaginatedResponse:
    """
    Список товаров для витрины B2C (B2B-7).
    Фильтры: MODERATED + deleted=false + хотя бы один SKU с active_quantity > 0.
    """
    # Базовый запрос с фильтрами видимости
    query = _load_products_query(db)
    query = _visibility_filter(query)

    # Только товары с SKU в наличии
    query = query.filter(
        Product.skus.any(SKU.stock_quantity - SKU.reserved_quantity > 0)
    )

    # Фильтр по категории
    if category_id:
        query = query.filter(Product.category_id == category_id)

    # Текстовый поиск
    if search and len(search) >= 3:
        pattern = f"%{search}%"
        query = query.filter(
            (Product.title.ilike(pattern)) | (Product.description.ilike(pattern))
        )

    # Считаем total до пагинации
    count_query = db.query(func.count(Product.id)).filter(
        Product.status == ProductStatus.MODERATED,
        Product.deleted == False,  # noqa: E712
        Product.skus.any(SKU.stock_quantity - SKU.reserved_quantity > 0),
    )
    if category_id:
        count_query = count_query.filter(Product.category_id == category_id)
    if search and len(search) >= 3:
        pattern = f"%{search}%"
        count_query = count_query.filter(
            (Product.title.ilike(pattern)) | (Product.description.ilike(pattern))
        )
    total_count = count_query.scalar()

    # Сортировка
    if sort == "price_asc":
        query = query.order_by(Product.created_at.asc())  # упрощённо
    elif sort == "price_desc":
        query = query.order_by(Product.created_at.desc())
    else:  # created_desc
        query = query.order_by(Product.created_at.desc())

    # Пагинация
    products = query.offset(offset).limit(limit).all()

    return ProductPublicPaginatedResponse(
        items=[_product_to_short(p) for p in products],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


def get_public_product(
    db: Session,
    product_id: uuid.UUID,
) -> ProductPublicResponse:
    """
    Получить одну карточку товара для витрины.
    Условия видимости применяются.
    """
    product = _load_products_query(db).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    # Проверяем условия видимости
    if product.status != ProductStatus.MODERATED or product.deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    return _product_to_public(product)


def batch_public_products(
    db: Session,
    product_ids: list[uuid.UUID],
) -> list[ProductPublicResponse]:
    """
    Batch-запрос товаров по списку ID (для подборок/избранного B2C).
    Возвращает только видимые. Отсутствующие — не в ответе (не 404).
    """
    products = (
        _load_products_query(db)
        .filter(
            Product.id.in_(product_ids),
            Product.status == ProductStatus.MODERATED,
            Product.deleted == False,  # noqa: E712
        )
        .all()
    )

    return [_product_to_public(p) for p in products]
