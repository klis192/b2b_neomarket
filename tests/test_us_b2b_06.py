"""
Тесты для US-B2B-06: Создание и приёмка накладной.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
INVOICES_URL = "/api/v1/invoices"


def _create_moderated_product_with_sku(client, auth_headers, category_id: str, db) -> tuple:
    """Хелпер: создаёт MODERATED товар + SKU. Возвращает (product, sku)."""
    from src.models.product import Product, ProductStatus

    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    sku = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г зерно",
        "price": 89000,
    }, headers=auth_headers).json()

    # Ставим MODERATED (в реальности это делает модерация)
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    return product, sku


def test_create_invoice_with_moderated_sku_returns_201(
    client, auth_headers, seed_categories, db
):
    """Создание накладной для MODERATED товара → 201 CREATED."""
    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    resp = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers)

    assert resp.status_code == 201
    body = resp.json()

    assert body["status"] == "CREATED"
    assert len(body["items"]) == 1
    assert body["items"][0]["sku_id"] == sku["id"]
    assert body["items"][0]["quantity"] == 10
    assert body["items"][0]["accepted_quantity"] is None
    assert "id" in body
    assert "seller_id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_non_moderated_sku_returns_400(
    client, auth_headers, seed_categories
):
    """Накладная для НЕ MODERATED товара → 400."""
    # Товар в ON_MODERATION (после создания SKU)
    product = client.post(PRODUCTS_URL, json={
        "title": "Товар на модерации",
        "description": "Описание",
        "category_id": seed_categories["mono_id"],
        "images": [{"url": "/s3/test.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    sku = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "SKU",
        "price": 50000,
    }, headers=auth_headers).json()

    # Товар в ON_MODERATION — не MODERATED
    resp = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 5}],
    }, headers=auth_headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"
    assert "MODERATED" in resp.json()["message"]


def test_others_sku_returns_403(
    client, auth_headers, other_auth_headers, seed_categories, db
):
    """Накладная с чужим SKU → 403 NOT_OWNER."""
    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    # Другой продавец пытается создать накладную с чужим SKU
    resp = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 5}],
    }, headers=other_auth_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_OWNER"


def test_nonexistent_sku_returns_404(client, auth_headers):
    """Несуществующий SKU → 404."""
    resp = client.post(INVOICES_URL, json={
        "items": [{"sku_id": str(uuid.uuid4()), "quantity": 5}],
    }, headers=auth_headers)

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_accept_full_increases_stock_quantity(
    client, auth_headers, seed_categories, db
):
    """Полная приёмка → stock_quantity += quantity, статус ACCEPTED."""
    from src.models.sku import SKU as SKUModel

    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    # Создаём накладную
    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()

    # Полная приёмка (пустое тело)
    resp = client.post(f"{INVOICES_URL}/{inv['id']}/accept")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACCEPTED"
    assert body["items"][0]["accepted_quantity"] == 10
    assert body["accepted_at"] is not None

    # Проверяем stock_quantity в БД
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.stock_quantity == 10


def test_accept_partial(
    client, auth_headers, seed_categories, db
):
    """Частичная приёмка → PARTIALLY_ACCEPTED, stock_quantity += accepted_quantity."""
    from src.models.sku import SKU as SKUModel

    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()

    # Частичная приёмка: принимаем 7 из 10
    item_id = inv["items"][0]["id"]
    resp = client.post(f"{INVOICES_URL}/{inv['id']}/accept", json={
        "accepted_items": [
            {"invoice_item_id": item_id, "accepted_quantity": 7},
        ],
    })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PARTIALLY_ACCEPTED"
    assert body["items"][0]["accepted_quantity"] == 7

    # stock_quantity обновился на 7
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.stock_quantity == 7


def test_accept_zero_cancelled(
    client, auth_headers, seed_categories, db
):
    """Все accepted_quantity == 0 → CANCELLED."""
    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()

    item_id = inv["items"][0]["id"]
    resp = client.post(f"{INVOICES_URL}/{inv['id']}/accept", json={
        "accepted_items": [
            {"invoice_item_id": item_id, "accepted_quantity": 0},
        ],
    })

    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_accept_already_accepted_returns_409(
    client, auth_headers, seed_categories, db
):
    """Повторная приёмка → 409 CONFLICT."""
    product, sku = _create_moderated_product_with_sku(
        client, auth_headers, seed_categories["mono_id"], db
    )

    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()

    # Первая приёмка — OK
    client.post(f"{INVOICES_URL}/{inv['id']}/accept")

    # Повторная — 409
    resp = client.post(f"{INVOICES_URL}/{inv['id']}/accept")
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


def test_create_invoice_without_auth_returns_401(client):
    """Без токена → 401."""
    resp = client.post(INVOICES_URL, json={
        "items": [{"sku_id": str(uuid.uuid4()), "quantity": 5}],
    })
    assert resp.status_code == 401


def test_empty_items_returns_400(client, auth_headers):
    """Пустой items → 400."""
    resp = client.post(INVOICES_URL, json={"items": []}, headers=auth_headers)
    assert resp.status_code == 400
