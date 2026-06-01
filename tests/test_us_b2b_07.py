"""
Тесты для US-B2B-07: Каталог для B2C (service-to-service).
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
PUBLIC_URL = "/api/v1/public/products"
INVOICES_URL = "/api/v1/invoices"


def _create_moderated_product_with_stock(client, auth_headers, service_headers, category_id, db):
    """Хелпер: создаёт MODERATED товар с SKU в наличии (stock > 0)."""
    from src.models.product import Product, ProductStatus

    # Создаём товар + SKU
    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт с нотами жасмина",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
        "characteristics": [{"name": "Страна", "value": "Эфиопия"}],
    }, headers=auth_headers).json()

    sku = client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г зерно",
        "price": 89000,
        "cost_price": 45000,
        "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    # Ставим MODERATED
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    # Создаём накладную и принимаем (stock += 10)
    inv = client.post(INVOICES_URL, json={
        "items": [{"sku_id": sku["id"], "quantity": 10}],
    }, headers=auth_headers).json()
    client.post(f"{INVOICES_URL}/{inv['id']}/accept", headers=auth_headers)

    return product, sku


def test_catalog_returns_moderated_in_stock_products(
    client, auth_headers, service_headers, seed_categories, db
):
    """Каталог возвращает только MODERATED товары с SKU в наличии."""
    product, sku = _create_moderated_product_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db
    )

    resp = client.get(PUBLIC_URL, headers=service_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] >= 1
    assert len(body["items"]) >= 1
    assert "limit" in body
    assert "offset" in body

    # Первый товар — наш
    found = [p for p in body["items"] if p["id"] == product["id"]]
    assert len(found) == 1
    assert found[0]["title"] == "Эфиопия Иргачеффе"
    assert found[0]["min_price"] is not None


def test_catalog_response_has_no_cost_price(
    client, auth_headers, service_headers, seed_categories, db
):
    """Публичный каталог НЕ содержит cost_price и reserved_quantity в SKU."""
    product, sku = _create_moderated_product_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db
    )

    # Получаем полную карточку
    resp = client.get(f"{PUBLIC_URL}/{product['id']}", headers=service_headers)

    assert resp.status_code == 200
    body = resp.json()

    # SKU не содержит cost_price и reserved_quantity
    for s in body["skus"]:
        assert "cost_price" not in s
        assert "reserved_quantity" not in s
        # Но содержит публичные поля
        assert "price" in s
        assert "active_quantity" in s
        assert "stock_quantity" in s


def test_catalog_missing_service_key_returns_401(client):
    """Без X-Service-Key → 401."""
    resp = client.get(PUBLIC_URL)
    assert resp.status_code == 401


def test_catalog_hides_deleted_products(
    client, auth_headers, service_headers, seed_categories, db
):
    """Удалённые товары не видны в каталоге."""
    product, sku = _create_moderated_product_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db
    )

    # Удаляем товар
    client.delete(f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers)

    # В каталоге его нет
    resp = client.get(PUBLIC_URL, headers=service_headers)
    found = [p for p in resp.json()["items"] if p["id"] == product["id"]]
    assert len(found) == 0


def test_catalog_hides_non_moderated_products(
    client, auth_headers, service_headers, seed_categories
):
    """Товары НЕ в статусе MODERATED не видны."""
    # Создаём товар + SKU (статус ON_MODERATION)
    product = client.post(PRODUCTS_URL, json={
        "title": "Не промодерированный",
        "description": "Описание",
        "category_id": seed_categories["mono_id"],
        "images": [{"url": "/s3/test.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "SKU",
        "price": 50000,
    }, headers=auth_headers)

    resp = client.get(PUBLIC_URL, headers=service_headers)
    found = [p for p in resp.json()["items"] if p["id"] == product["id"]]
    assert len(found) == 0


def test_catalog_hides_out_of_stock_products(
    client, auth_headers, service_headers, seed_categories, db
):
    """Товары без SKU в наличии не видны."""
    from src.models.product import Product, ProductStatus

    product = client.post(PRODUCTS_URL, json={
        "title": "Без стока",
        "description": "Описание",
        "category_id": seed_categories["mono_id"],
        "images": [{"url": "/s3/test.jpg", "ordering": 0}],
    }, headers=auth_headers).json()

    client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "SKU",
        "price": 50000,
    }, headers=auth_headers)

    # MODERATED но stock = 0
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    resp = client.get(PUBLIC_URL, headers=service_headers)
    found = [p for p in resp.json()["items"] if p["id"] == product["id"]]
    assert len(found) == 0


def test_get_public_product_returns_full_card(
    client, auth_headers, service_headers, seed_categories, db
):
    """GET одного товара возвращает полную карточку с SKU."""
    product, sku = _create_moderated_product_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db
    )

    resp = client.get(f"{PUBLIC_URL}/{product['id']}", headers=service_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == product["id"]
    assert body["title"] == "Эфиопия Иргачеффе"
    assert len(body["skus"]) >= 1
    assert body["skus"][0]["active_quantity"] > 0


def test_get_public_nonexistent_returns_404(client, service_headers):
    """Несуществующий товар → 404."""
    resp = client.get(f"{PUBLIC_URL}/{uuid.uuid4()}", headers=service_headers)
    assert resp.status_code == 404


def test_batch_returns_only_visible(
    client, auth_headers, service_headers, seed_categories, db
):
    """Batch возвращает только видимые товары, невидимые — не в ответе."""
    product, sku = _create_moderated_product_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db
    )

    fake_id = str(uuid.uuid4())
    resp = client.post(
        f"{PUBLIC_URL}/batch",
        json={"product_ids": [product["id"], fake_id]},
        headers=service_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    # Только видимый товар в ответе
    ids = [p["id"] for p in body]
    assert product["id"] in ids
    assert fake_id not in ids
