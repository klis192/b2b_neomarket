"""
Тесты для US-B2B-05: Просмотр карточки + причины блокировки.
Два режима: seller (JWT) и service (X-Service-Key).
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"


def _create_product_with_sku(client, auth_headers, category_id: str) -> dict:
    """Хелпер: создаёт товар + SKU."""
    product = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт с нотами жасмина",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
        "characteristics": [{"name": "Страна", "value": "Эфиопия"}],
    }, headers=auth_headers).json()

    client.post(SKUS_URL, json={
        "product_id": product["id"],
        "name": "250г зерно",
        "price": 89000,
        "cost_price": 45000,
        "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
        "characteristics": [{"name": "Вес", "value": "250 г"}],
    }, headers=auth_headers)

    return product


def test_get_moderated_product_returns_full_payload(
    client, auth_headers, seed_categories, db
):
    """GET MODERATED товар — возвращает полный payload со всеми полями."""
    from src.models.product import Product, ProductStatus

    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Эмулируем модерацию
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.MODERATED
    db.commit()

    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()

    # Все обязательные поля по спеке
    assert body["id"] == product["id"]
    assert body["title"] == "Эфиопия Иргачеффе"
    assert body["description"] == "Яркий моносорт с нотами жасмина"
    assert body["status"] == "MODERATED"
    assert body["deleted"] is False
    assert "seller_id" in body
    assert "category_id" in body
    assert "slug" in body
    assert "created_at" in body
    assert "updated_at" in body

    # Нет блокировки — канон-поля
    assert body["blocking_reason_id"] is None
    assert body["moderator_comment"] is None
    assert body["blocked"] is False
    assert body["blocking_reason"] is None
    assert body["field_reports"] == []

    # SKU в ответе
    assert len(body["skus"]) == 1
    assert body["skus"][0]["name"] == "250г зерно"
    assert body["skus"][0]["price"] == 89000

    # Images и characteristics с id
    assert len(body["images"]) >= 1
    assert "id" in body["images"][0]
    assert len(body["characteristics"]) >= 1
    assert "id" in body["characteristics"][0]


def test_get_blocked_product_returns_blocking_reason_and_field_reports(
    client, auth_headers, seed_categories, db
):
    """GET BLOCKED товар — возвращает blocking_reason, field_reports, blocked=true (канон B2B-5)."""
    from src.models.product import Product, ProductStatus

    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Эмулируем блокировку — полный объект blocking_reason + field_reports
    reason_id = uuid.uuid4()
    db_product = db.query(Product).filter(
        Product.id == uuid.UUID(product["id"])
    ).first()
    db_product.status = ProductStatus.BLOCKED
    db_product.blocking_reason_id = reason_id
    db_product.moderator_comment = "Несоответствие описания и фотографий"
    db_product.blocking_reason = {
        "id": str(reason_id),
        "title": "Описание не соответствует товару",
        "comment": "Несоответствие описания и фотографий",
    }
    db_product.field_reports = [
        {"field_name": "description", "sku_id": None, "comment": "Текст не соответствует фото"},
    ]
    db.commit()

    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )

    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "BLOCKED"
    assert body["blocked"] is True
    assert body["blocking_reason_id"] == str(reason_id)
    assert body["moderator_comment"] == "Несоответствие описания и фотографий"
    # Канон-поля: полный объект причины и замечания по полям
    assert body["blocking_reason"]["title"] == "Описание не соответствует товару"
    assert len(body["field_reports"]) == 1
    assert body["field_reports"][0]["field_name"] == "description"


def test_get_others_product_returns_404(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Чужой товар → 404 (не раскрываем существование)."""
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=other_auth_headers
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_get_product_service_mode(
    client, auth_headers, seed_categories, service_headers
):
    """X-Service-Key — видит любые товары, ownership не проверяется."""
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Запрос от сервиса (не от продавца)
    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=service_headers
    )

    assert resp.status_code == 200
    assert resp.json()["id"] == product["id"]


def test_get_product_service_mode_sees_others(
    client, auth_headers, other_auth_headers, seed_categories, service_headers
):
    """Service mode видит товары любых продавцов."""
    # Товар первого продавца
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Второй продавец через JWT → 404
    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=other_auth_headers
    )
    assert resp.status_code == 404

    # Сервис → 200 (видит всё)
    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=service_headers
    )
    assert resp.status_code == 200


def test_get_nonexistent_returns_404(client, auth_headers):
    """Несуществующий товар → 404."""
    resp = client.get(
        f"{PRODUCTS_URL}/{uuid.uuid4()}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_get_product_without_auth_returns_401(client):
    """Без авторизации → 401."""
    resp = client.get(f"{PRODUCTS_URL}/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_get_deleted_product(
    client, auth_headers, seed_categories
):
    """Удалённый товар — seller всё равно видит (deleted=true)."""
    product = _create_product_with_sku(client, auth_headers, seed_categories["mono_id"])

    # Удаляем
    client.delete(f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers)

    # GET — видим с deleted=true
    resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
