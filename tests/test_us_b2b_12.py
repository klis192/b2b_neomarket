"""
Тесты для US-B2B-12: Удаление SKU.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
INVOICES_URL = "/api/v1/invoices"
RESERVE_URL = "/api/v1/inventory/reserve"


def _create_product_with_sku(client, auth_headers, category_id):
    """Хелпер: создаёт товар + SKU, возвращает (product, sku)."""
    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия",
        "description": "Моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/eth.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    sku = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г зерно",
        "price": 89000,
    }, headers=auth_headers).json()

    return product, sku


def test_delete_sku_with_active_reserves_returns_409(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    SKU с reserved_quantity > 0 → 409 CONFLICT.
    """
    from src.models.product import Product, ProductStatus

    product, sku = _create_product_with_sku(
        client, auth_headers, seed_categories["mono_id"]
    )

    # MODERATED + stock для резервирования
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()
    client.post(f"{INVOICES_URL}/{inv['id']}/accept", headers=auth_headers)

    # Резервируем 3
    client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    # Удаление → 409
    resp = client.delete(f"{SKUS_URL}/{sku['id']}", headers=auth_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


def test_last_sku_on_moderation_transitions_product_to_created(
    client, auth_headers, seed_categories, db
):
    """
    Удаление последнего SKU у товара ON_MODERATION →
    товар возвращается в CREATED + событие DELETED в Moderation.
    """
    from src.models.outbox import Outbox

    product, sku = _create_product_with_sku(
        client, auth_headers, seed_categories["mono_id"]
    )

    # Товар в ON_MODERATION (после первого SKU)
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.json()["status"] == "ON_MODERATION"

    # Удаляем единственный SKU
    resp = client.delete(f"{SKUS_URL}/{sku['id']}", headers=auth_headers)
    assert resp.status_code == 204

    # Товар вернулся в CREATED
    product_resp2 = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp2.json()["status"] == "CREATED"

    # Событие DELETED в outbox
    event = db.query(Outbox).filter(
        Outbox.event_type == "DELETED"
    ).first()
    assert event is not None
    assert event.payload["payload"]["product_id"] == product["id"]


def test_delete_sku_hard_blocked_returns_403(
    client, auth_headers, seed_categories, db
):
    """HARD_BLOCKED товар → 403 FORBIDDEN."""
    from src.models.product import Product, ProductStatus

    product, sku = _create_product_with_sku(
        client, auth_headers, seed_categories["mono_id"]
    )

    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.HARD_BLOCKED
    db.commit()

    resp = client.delete(f"{SKUS_URL}/{sku['id']}", headers=auth_headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_delete_others_sku_returns_403(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Чужой SKU → 403 NOT_OWNER."""
    product, sku = _create_product_with_sku(
        client, auth_headers, seed_categories["mono_id"]
    )

    resp = client.delete(f"{SKUS_URL}/{sku['id']}", headers=other_auth_headers)
    assert resp.status_code == 403


def test_delete_nonexistent_sku_returns_404(client, auth_headers):
    """Несуществующий SKU → 404."""
    resp = client.delete(f"{SKUS_URL}/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_sku_success(
    client, auth_headers, seed_categories
):
    """Успешное удаление SKU (без резервов, не последний)."""
    product, sku1 = _create_product_with_sku(
        client, auth_headers, seed_categories["mono_id"]
    )

    # Создаём второй SKU (чтобы первый не был последним)
    sku2 = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "1кг зерно",
        "price": 320000,
    }, headers=auth_headers).json()

    # Удаляем первый
    resp = client.delete(f"{SKUS_URL}/{sku1['id']}", headers=auth_headers)
    assert resp.status_code == 204

    # Товар остался в ON_MODERATION (ещё есть SKU)
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.json()["status"] == "ON_MODERATION"


def test_delete_sku_without_auth_returns_401(client):
    """Без токена → 401."""
    resp = client.delete(f"{SKUS_URL}/{uuid.uuid4()}")
    assert resp.status_code == 401
