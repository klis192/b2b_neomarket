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
    """Валидный запрос на создание SKU (по спеке: required = product_id, name, price)."""
    return {
        "product_id": product_id,
        "name": "250г зерно",
        "price": 89000,
        "discount": 0,
        "cost_price": 45000,
        "article": "ETH-250-BEAN",
        "images": [
            {"url": "/s3/ethiopia-250g.jpg", "ordering": 0},
        ],
        "characteristics": [
            {"name": "Вес", "value": "250 г"},
            {"name": "Помол", "value": "Зерно"},
        ],
    }


def test_first_sku_transitions_product_to_on_moderation(
    client, auth_headers, seed_categories, db
):
    """
    Первый SKU → товар CREATED → ON_MODERATION + событие CREATED в outbox.
    """
    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    assert product["status"] == "CREATED"

    # Добавляем первый SKU
    sku_data = _valid_sku(product["id"])
    resp = client.post(SKUS_URL, json=sku_data, headers=auth_headers)

    assert resp.status_code == 201
    sku = resp.json()

    # Проверяем все обязательные поля SKUResponse по спеке
    assert sku["name"] == "250г зерно"
    assert sku["price"] == 89000
    assert sku["discount"] == 0
    assert sku["cost_price"] == 45000
    assert sku["stock_quantity"] == 0
    assert sku["active_quantity"] == 0
    assert sku["reserved_quantity"] == 0
    assert sku["article"] == "ETH-250-BEAN"
    assert len(sku["images"]) == 1
    assert "id" in sku["images"][0]
    assert len(sku["characteristics"]) == 2
    assert "id" in sku["characteristics"][0]
    assert "created_at" in sku
    assert "updated_at" in sku

    # Проверяем что товар перешёл в ON_MODERATION
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.status_code == 200
    assert product_resp.json()["status"] == "ON_MODERATION"

    # Проверяем запись в outbox (событие CREATED для Moderation)
    from src.models.outbox import Outbox
    outbox_event = db.query(Outbox).filter(Outbox.event_type == "CREATED").first()
    assert outbox_event is not None
    assert str(outbox_event.payload["product_id"]) == product["id"]


def test_second_sku_no_state_change(
    client, auth_headers, seed_categories
):
    """Второй SKU — статус товара не меняется."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Первый SKU → ON_MODERATION
    client.post(SKUS_URL, json=_valid_sku(product["id"]), headers=auth_headers)

    # Второй SKU
    sku2 = {
        **_valid_sku(product["id"]),
        "name": "1кг зерно",
        "price": 320000,
        "article": "ETH-1KG-BEAN",
        "images": [{"url": "/s3/ethiopia-1kg.jpg", "ordering": 0}],
    }
    resp = client.post(SKUS_URL, json=sku2, headers=auth_headers)
    assert resp.status_code == 201

    # Статус всё ещё ON_MODERATION
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.json()["status"] == "ON_MODERATION"


def test_add_sku_to_hard_blocked_returns_403(
    client, auth_headers, seed_categories, db
):
    """HARD_BLOCKED товар → 403."""
    from src.models.product import Product, ProductStatus

    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Принудительно ставим HARD_BLOCKED
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.HARD_BLOCKED
    db.commit()

    resp = client.post(SKUS_URL, json=_valid_sku(product["id"]), headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_add_sku_to_nonexistent_product_returns_404(client, auth_headers):
    """Несуществующий товар → 404."""
    resp = client.post(SKUS_URL, json=_valid_sku(str(uuid.uuid4())), headers=auth_headers)
    assert resp.status_code == 404


def test_add_sku_to_others_product_returns_404(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Чужой товар → 404 (не раскрываем существование)."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    resp = client.post(SKUS_URL, json=_valid_sku(product["id"]), headers=other_auth_headers)
    assert resp.status_code == 404


def test_create_sku_without_auth_returns_401(client):
    """Без токена → 401."""
    resp = client.post(SKUS_URL, json=_valid_sku(str(uuid.uuid4())))
    assert resp.status_code == 401


def test_create_sku_minimal_fields(
    client, auth_headers, seed_categories
):
    """Минимальный запрос — только required поля (product_id, name, price)."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    resp = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "Минимальный SKU",
        "price": 50000,
    }, headers=auth_headers)

    assert resp.status_code == 201
    sku = resp.json()
    assert sku["cost_price"] is None  # nullable по спеке
    assert sku["article"] is None
    assert sku["images"] == []
    assert sku["discount"] == 0
