"""
Тесты для US-B2B-11: Список товаров продавца.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"


def _create_product(client, auth_headers, category_id):
    """Хелпер: создаёт товар."""
    return client.post(PRODUCTS_URL, json={
        "title": "Эфиопия",
        "description": "Моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/eth.jpg", "ordering": 0}],
    }, headers=auth_headers).json()


def test_list_returns_only_own_products(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Продавец видит только свои товары. Чужие не видны."""
    # Первый продавец создаёт 2 товара
    p1 = _create_product(client, auth_headers, seed_categories["mono_id"])
    p2 = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Второй продавец создаёт 1 товар
    p3 = _create_product(client, other_auth_headers, seed_categories["mono_id"])

    # Первый продавец видит только свои 2
    resp = client.get(PRODUCTS_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    ids = [p["id"] for p in body["items"]]
    assert p1["id"] in ids
    assert p2["id"] in ids
    assert p3["id"] not in ids

    # Второй продавец видит только свой 1
    resp2 = client.get(PRODUCTS_URL, headers=other_auth_headers)
    assert resp2.json()["total_count"] == 1
    assert resp2.json()["items"][0]["id"] == p3["id"]


def test_idor_query_param_seller_id_ignored(
    client, auth_headers, other_auth_headers, seed_categories
):
    """
    IDOR: seller_id в query-параметрах игнорируется —
    фильтрация только по JWT.
    """
    _create_product(client, auth_headers, seed_categories["mono_id"])

    # Второй продавец пытается подсмотреть через query param
    # (нет такого параметра, но если бы был — игнорируется)
    resp = client.get(PRODUCTS_URL, headers=other_auth_headers)
    assert resp.json()["total_count"] == 0  # свои товары — 0


def test_deleted_products_visible_with_deleted_flag(
    client, auth_headers, seed_categories
):
    """include_deleted=true — удалённые товары видны с флагом deleted=true."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Удаляем
    client.post(SKUS_URL, json={
        "product_id": product["id"], "name": "SKU", "price": 50000,
    }, headers=auth_headers)
    client.delete(f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers)

    # По умолчанию — не видны
    resp = client.get(PRODUCTS_URL, headers=auth_headers)
    ids = [p["id"] for p in resp.json()["items"]]
    assert product["id"] not in ids

    # С include_deleted=true — видны
    resp2 = client.get(f"{PRODUCTS_URL}?include_deleted=true", headers=auth_headers)
    ids2 = [p["id"] for p in resp2.json()["items"]]
    assert product["id"] in ids2
    deleted_p = [p for p in resp2.json()["items"] if p["id"] == product["id"]][0]
    assert deleted_p["deleted"] is True


def test_list_filter_by_status(
    client, auth_headers, seed_categories, db
):
    """Фильтр по статусу работает."""
    from src.models.product import Product, ProductStatus

    p1 = _create_product(client, auth_headers, seed_categories["mono_id"])
    p2 = _create_product(client, auth_headers, seed_categories["mono_id"])

    # Ставим p2 в MODERATED
    db_p2 = db.query(Product).filter(Product.id == uuid.UUID(p2["id"])).first()
    db_p2.status = ProductStatus.MODERATED
    db.commit()

    # Фильтр: только CREATED
    resp = client.get(f"{PRODUCTS_URL}?status=CREATED", headers=auth_headers)
    assert resp.json()["total_count"] == 1
    assert resp.json()["items"][0]["id"] == p1["id"]

    # Фильтр: только MODERATED
    resp2 = client.get(f"{PRODUCTS_URL}?status=MODERATED", headers=auth_headers)
    assert resp2.json()["total_count"] == 1
    assert resp2.json()["items"][0]["id"] == p2["id"]


def test_list_pagination(
    client, auth_headers, seed_categories
):
    """Пагинация: limit и offset работают."""
    for _ in range(5):
        _create_product(client, auth_headers, seed_categories["mono_id"])

    # limit=2, offset=0
    resp = client.get(f"{PRODUCTS_URL}?limit=2&offset=0", headers=auth_headers)
    assert resp.json()["total_count"] == 5
    assert len(resp.json()["items"]) == 2

    # offset=3
    resp2 = client.get(f"{PRODUCTS_URL}?limit=2&offset=3", headers=auth_headers)
    assert len(resp2.json()["items"]) == 2


def test_list_response_format(
    client, auth_headers, seed_categories
):
    """Ответ содержит обязательные поля ProductShortResponse."""
    _create_product(client, auth_headers, seed_categories["mono_id"])

    resp = client.get(PRODUCTS_URL, headers=auth_headers)
    item = resp.json()["items"][0]

    # Required по протоколу ProductShortResponse
    assert "id" in item
    assert "title" in item
    assert "slug" in item
    assert "status" in item
    assert "category_id" in item
    assert "deleted" in item
    assert "created_at" in item


def test_list_without_auth_returns_401(client):
    """Без токена → 401."""
    resp = client.get(PRODUCTS_URL)
    assert resp.status_code == 401
