"""
Тесты для US-B2B-10: Fulfill при доставке.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
INVOICES_URL = "/api/v1/invoices"
RESERVE_URL = "/api/v1/inventory/reserve"
FULFILL_URL = "/api/v1/inventory/fulfill"


def _create_reserved_sku(client, auth_headers, service_headers, category_id, db, stock=10, reserve_qty=3):
    """Хелпер: MODERATED товар + SKU со стоком + зарезервировано reserve_qty."""
    from src.models.product import Product, ProductStatus

    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия",
        "description": "Моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/eth.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    sku = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г",
        "price": 89000,
    }, headers=auth_headers).json()

    # MODERATED
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    # Накладная → stock
    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": stock}],
    }, headers=auth_headers).json()
    client.post(f"{INVOICES_URL}/{inv['id']}/accept", headers=auth_headers)

    # Резервируем
    order_id = str(uuid.uuid4())
    if reserve_qty > 0:
        client.post(RESERVE_URL, json={
            "idempotency_key": str(uuid.uuid4()),
            "order_id": order_id,
            "items": [{"sku_id": sku["id"], "quantity": reserve_qty}],
        }, headers=service_headers)

    return product, sku, order_id


def test_fulfill_decreases_reserved_quantity(
    client, auth_headers, service_headers, seed_categories, db
):
    """Fulfill уменьшает reserved_quantity."""
    product, sku, order_id = _create_reserved_sku(
        client, auth_headers, service_headers,
        seed_categories["mono_id"], db, stock=10, reserve_qty=3,
    )

    resp = client.post(FULFILL_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FULFILLED"
    assert "processed_at" in body

    # Проверяем в БД: reserved=0, stock=7 (10-3)
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 0
    assert db_sku.stock_quantity == 7


def test_active_quantity_unchanged(
    client, auth_headers, service_headers, seed_categories, db
):
    """active_quantity не меняется после fulfill (stock и reserved уменьшаются одинаково)."""
    product, sku, order_id = _create_reserved_sku(
        client, auth_headers, service_headers,
        seed_categories["mono_id"], db, stock=10, reserve_qty=3,
    )

    # До fulfill: stock=10, reserved=3, active=7
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    active_before = db_sku.active_quantity
    assert active_before == 7

    # Fulfill
    client.post(FULFILL_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    # После fulfill: stock=7, reserved=0, active=7 (не изменился)
    db.refresh(db_sku)
    assert db_sku.active_quantity == 7
    assert db_sku.active_quantity == active_before


def test_idempotent_fulfill_no_double_deduction(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    Идемпотентность: повторный fulfill с тем же order_id
    не списывает дважды.
    """
    product, sku, order_id = _create_reserved_sku(
        client, auth_headers, service_headers,
        seed_categories["mono_id"], db, stock=10, reserve_qty=3,
    )

    payload = {
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }

    # Первый fulfill
    resp1 = client.post(FULFILL_URL, json=payload, headers=service_headers)
    assert resp1.status_code == 200

    # Повторный — идемпотентный
    resp2 = client.post(FULFILL_URL, json=payload, headers=service_headers)
    assert resp2.status_code == 200
    assert resp2.json() == resp1.json()

    # В БД: stock=7, reserved=0 (не stock=4, reserved=-3)
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.stock_quantity == 7
    assert db_sku.reserved_quantity == 0


def test_fulfill_more_than_reserved_returns_409(
    client, auth_headers, service_headers, seed_categories, db
):
    """Fulfill больше чем зарезервировано → 409."""
    product, sku, order_id = _create_reserved_sku(
        client, auth_headers, service_headers,
        seed_categories["mono_id"], db, stock=10, reserve_qty=3,
    )

    resp = client.post(FULFILL_URL, json={
        "order_id": str(uuid.uuid4()),  # другой order_id чтобы не было идемпотентности
        "items": [{"sku_id": sku["id"], "quantity": 100}],
    }, headers=service_headers)

    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


def test_fulfill_without_service_key_returns_401(client):
    """Без X-Service-Key → 401."""
    resp = client.post(FULFILL_URL, json={
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    })
    assert resp.status_code == 401


def test_fulfill_nonexistent_sku_returns_404(client, service_headers):
    """Несуществующий SKU → 404."""
    resp = client.post(FULFILL_URL, json={
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    }, headers=service_headers)
    assert resp.status_code == 404
