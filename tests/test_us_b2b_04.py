"""
Тесты для US-B2B-04: Удаление товара (soft delete).
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"


def _create_product_with_sku(client, auth_headers, category_id: str) -> dict:
    """Хелпер: создаёт товар + SKU."""
    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г зерно",
        "price": 89000,
    }, headers=auth_headers)

    return product


def test_delete_sets_deleted_true(
    client, auth_headers, seed_categories, db
):
    """Удаление ставит deleted=true + события в outbox."""
    from src.models.outbox import Outbox

    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    resp = client.delete(
        f"{PRODUCTS_URL}/{product['id']}",
        headers=auth_headers,
    )

    assert resp.status_code == 204

    # Проверяем что товар помечен удалённым
    get_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["deleted"] is True

    # Событие DELETED → Moderation
    deleted_event = db.query(Outbox).filter(Outbox.event_type == "DELETED").first()
    assert deleted_event is not None
    assert str(deleted_event.payload["product_id"]) == product["id"]

    # Событие PRODUCT_DELETED → B2C
    b2c_event = db.query(Outbox).filter(Outbox.event_type == "PRODUCT_DELETED").first()
    assert b2c_event is not None
    assert str(b2c_event.payload["product_id"]) == product["id"]
    assert isinstance(b2c_event.payload["sku_ids"], list)


def test_delete_already_deleted_returns_400(
    client, auth_headers, seed_categories
):
    """Повторное удаление → 400."""
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Первое удаление — ОК
    client.delete(f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers)

    # Повторное — 400
    resp = client.delete(
        f"{PRODUCTS_URL}/{product['id']}",
        headers=auth_headers,
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_delete_others_product_returns_403(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Удаление чужого товара → 403 NOT_OWNER."""
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    resp = client.delete(
        f"{PRODUCTS_URL}/{product['id']}",
        headers=other_auth_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_OWNER"


def test_delete_nonexistent_returns_404(client, auth_headers):
    """Несуществующий товар → 404."""
    resp = client.delete(
        f"{PRODUCTS_URL}/{uuid.uuid4()}",
        headers=auth_headers,
    )

    assert resp.status_code == 404


def test_delete_hard_blocked_returns_403(
    client, auth_headers, seed_categories, db
):
    """HARD_BLOCKED товар → 403."""
    from src.models.product import Product, ProductStatus

    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.HARD_BLOCKED
    db.commit()

    resp = client.delete(
        f"{PRODUCTS_URL}/{product['id']}",
        headers=auth_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_delete_without_auth_returns_401(client, seed_categories):
    """Без токена → 401."""
    resp = client.delete(f"{PRODUCTS_URL}/{uuid.uuid4()}")
    assert resp.status_code == 401
