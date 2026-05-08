"""
Тесты для US-B2B-02: Добавление SKU.
Имена тестов — из контракта.
"""

import uuid

import pytest


PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"


def _create_product(client, auth_headers, category_id: str) -> dict:
    """Хелпер: создаёт товар и возвращает ответ."""
    data = {
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
        "characteristics": [{"name": "Страна", "value": "Эфиопия"}],
    }
    resp = client.post(PRODUCTS_URL, json=data, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


def _valid_sku(product_id: str) -> dict:
    """Валидный запрос на создание SKU."""
    return {
        "product_id": product_id,
        "name": "250г зерно",
        "price": 89000,
        "cost_price": 45000,
        "discount": 0,
        "image": "/s3/ethiopia-250g.jpg",
        "characteristics": [
            {"name": "Вес", "value": "250 г"},
            {"name": "Помол", "value": "Зерно"},
        ],
    }


def test_first_sku_transitions_product_to_on_moderation(
    client, auth_headers, seed_categories
):
    """
    Первый SKU для товара в статусе CREATED → товар переходит в ON_MODERATION.
    """
    # Создаём товар (статус = CREATED)
    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    assert product["status"] == "CREATED"

    # Добавляем первый SKU
    sku_data = _valid_sku(product["id"])
    resp = client.post(SKUS_URL, json=sku_data, headers=auth_headers)

    assert resp.status_code == 201
    sku = resp.json()

    # Проверяем SKU
    assert sku["name"] == "250г зерно"
    assert sku["price"] == 89000
    assert sku["cost_price"] == 45000
    assert sku["active_quantity"] == 0
    assert sku["reserved_quantity"] == 0
    assert sku["image"] == "/s3/ethiopia-250g.jpg"
    assert len(sku["characteristics"]) == 2

    # Проверяем что товар перешёл в ON_MODERATION
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.status_code == 200
    assert product_resp.json()["status"] == "ON_MODERATION"


def test_second_sku_no_state_change(
    client, auth_headers, seed_categories
):
    """
    Второй SKU — просто добавляется, статус товара не меняется.
    """
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Первый SKU → ON_MODERATION
    sku1 = _valid_sku(product["id"])
    client.post(SKUS_URL, json=sku1, headers=auth_headers)

    # Второй SKU — статус не должен измениться
    sku2 = {
        **_valid_sku(product["id"]),
        "name": "1кг зерно",
        "price": 320000,
        "cost_price": 160000,
        "image": "/s3/ethiopia-1kg.jpg",
    }
    resp = client.post(SKUS_URL, json=sku2, headers=auth_headers)
    assert resp.status_code == 201

    # Статус всё ещё ON_MODERATION (не изменился)
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.json()["status"] == "ON_MODERATION"


def test_add_sku_to_hard_blocked_returns_403(
    client, auth_headers, seed_categories, db
):
    """
    Добавление SKU к HARD_BLOCKED товару → 403.
    """
    from src.models.product import Product, ProductStatus

    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Принудительно ставим HARD_BLOCKED (в реальности это делает модерация)
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.HARD_BLOCKED
    db.commit()

    # Пытаемся добавить SKU
    sku_data = _valid_sku(product["id"])
    resp = client.post(SKUS_URL, json=sku_data, headers=auth_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_add_sku_to_nonexistent_product_returns_404(
    client, auth_headers
):
    """SKU для несуществующего товара → 404."""
    sku_data = _valid_sku(str(uuid.uuid4()))
    resp = client.post(SKUS_URL, json=sku_data, headers=auth_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_add_sku_to_others_product_returns_404(
    client, auth_headers, other_auth_headers, seed_categories
):
    """SKU к чужому товару → 404 (не раскрываем существование)."""
    # Первый продавец создаёт товар
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Второй продавец пытается добавить SKU
    sku_data = _valid_sku(product["id"])
    resp = client.post(SKUS_URL, json=sku_data, headers=other_auth_headers)

    assert resp.status_code == 404


def test_create_sku_without_auth_returns_401(client, seed_categories):
    """Без токена → 401."""
    sku_data = _valid_sku(str(uuid.uuid4()))
    resp = client.post(SKUS_URL, json=sku_data)

    assert resp.status_code == 401
