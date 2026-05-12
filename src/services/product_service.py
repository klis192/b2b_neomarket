"""
Бизнес-логика для товаров.
US-B2B-01: создание карточки товара.
"""

import uuid

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
from src.schemas.product import ProductCreate, ProductResponse


def _product_to_response(product: Product) -> ProductResponse:
    """Конвертирует ORM-объект в ответ API, формат из openapi."""
    return ProductResponse(
        id=str(product.id),
        title=product.title,
        description=product.description,
        status=product.status.value,
        deleted=product.deleted,
        blocked=product.status in (ProductStatus.BLOCKED, ProductStatus.HARD_BLOCKED),
        category_id=str(product.category_id),
        category_name=product.category.name if product.category else None,
        images=[
            {"url": img.url, "ordering": img.ordering}
            for img in sorted(product.images, key=lambda x: x.ordering)
        ],
        characteristics=[
            {"name": c.name, "value": c.value}
            for c in product.characteristics
        ],
        skus=[
            {
                "id": str(sku.id),
                "product_id": str(sku.product_id),
                "name": sku.name,
                "price": sku.price,
                "cost_price": sku.cost_price,
                "discount": sku.discount,
                "image": sku.image,
                "active_quantity": sku.active_quantity,
                "reserved_quantity": sku.reserved_quantity,
                "characteristics": [
                    {"name": c.name, "value": c.value}
                    for c in sku.characteristics
                ],
            }
            for sku in product.skus
        ],
    )


def get_product_by_id(
    db: Session,
    product_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> ProductResponse:
    """
    Получить товар по ID (для seller-а).
    Проверяет ownership — чужой товар → 404.
    """
    product = (
        db.query(Product)
        .options(
            joinedload(Product.category),
            joinedload(Product.images),
            joinedload(Product.characteristics),
            joinedload(Product.skus).subqueryload(SKU.characteristics),
        )
        .filter(
            Product.id == product_id,
            Product.seller_id == seller_id,
        )
        .first()
    )

    if not product:
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
    seller_id берётся из JWT — защита от IDOR.
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
        description=data.description,
        category_id=data.category_id,
        status=ProductStatus.CREATED,
    )
    db.add(product)
    db.flush()  # получаем product.id

    # Добавляем фото
    for img in data.images:
        db.add(ProductImage(
            product_id=product.id,
            url=img.url,
            ordering=img.ordering,
        ))

    # Добавляем характеристики
    for char in data.characteristics:
        db.add(ProductCharacteristic(
            product_id=product.id,
            name=char.name,
            value=char.value,
        ))

    db.commit()

    # Формируем ответ из данных, которые у нас уже есть
    # (Не делаем db.refresh — обходим несовместимость SQLite с UUID)
    return ProductResponse(
        id=str(product.id),
        title=data.title,
        description=data.description,
        status=ProductStatus.CREATED.value,
        deleted=False,
        blocked=False,
        category_id=str(category.id),
        category_name=category.name,
        images=[
            {"url": img.url, "ordering": img.ordering}
            for img in data.images
        ],
        characteristics=[
            {"name": c.name, "value": c.value}
            for c in data.characteristics
        ],
        skus=[],
    )
