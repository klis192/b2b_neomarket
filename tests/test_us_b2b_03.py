"""
Тесты для US-B2B-03: Редактирование товара/SKU.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"


def _create_product(client, auth_headers, category_id: str) -> dict:
    """Хелпер: создаёт товар."""
    resp = client.post(PRODUCTS_URL, json={
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт",
        "category_id": category_id,
        "images": [{"url": "/s3/ethiopia.jpg", "ordering": 0}],
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


def _create_sku(client, auth_headers, product_id: str) -> dict:
    """Хелпер: создаёт SKU для товара."""
    resp = client.post(SKUS_URL, json={
        "product_id": product_id,
        "name": "250г зерно",
        "price": 89000,
        "images": [{"url": "/s3/sku.jpg", "ordering": 0}],
    }, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


def _set_product_status(db, product_id: str, status):
    """Хелпер: принудительно ставит статус товара (эмулирует модерацию)."""
    from src.models.product import Product
    product = db.query(Product).filter(Product.id == uuid.UUID(product_id)).first()
    product.status = status
    db.commit()


def test_edit_moderated_product_returns_to_on_moderation(
    client, auth_headers, seed_categories, db
):
    """
    Редактирование MODERATED товара → статус ON_MODERATION + событие EDITED в outbox.
    """
    from src.models.product import ProductStatus
    from src.models.outbox import Outbox

    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    _create_sku(client, auth_headers, product["id"])

    # Эмулируем модерацию — ставим MODERATED
    _set_product_status(db, product["id"], ProductStatus.MODERATED)

    # Редактируем товар
    resp = client.patch(
        f"{PRODUCTS_URL}/{product['id']}",
        json={"title": "Эфиопия Иргачеффе (обновлено)"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Эфиопия Иргачеффе (обновлено)"
    assert body["status"] == "ON_MODERATION"

    # Проверяем событие EDITED в outbox
    outbox_event = db.query(Outbox).filter(Outbox.event_type == "EDITED").first()
    assert outbox_event is not None
    assert str(outbox_event.payload["product_id"]) == product["id"]


def test_edit_blocked_product_returns_to_on_moderation(
    client, auth_headers, seed_categories, db
):
    """Редактирование BLOCKED товара → ON_MODERATION (исправление после блокировки)."""
    from src.models.product import ProductStatus

    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    _create_sku(client, auth_headers, product["id"])
    _set_product_status(db, product["id"], ProductStatus.BLOCKED)

    resp = client.patch(
        f"{PRODUCTS_URL}/{product['id']}",
        json={"description": "Исправленное описание"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ON_MODERATION"
    # Данные блокировки очищены
    assert resp.json()["blocking_reason_id"] is None
    assert resp.json()["moderator_comment"] is None


def test_edit_hard_blocked_returns_403(
    client, auth_headers, seed_categories, db
):
    """HARD_BLOCKED → 403 FORBIDDEN."""
    from src.models.product import ProductStatus

    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    _set_product_status(db, product["id"], ProductStatus.HARD_BLOCKED)

    resp = client.patch(
        f"{PRODUCTS_URL}/{product['id']}",
        json={"title": "Попытка редактирования"},
        headers=auth_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "FORBIDDEN"


def test_edit_others_product_returns_403(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Редактирование чужого товара → 403 NOT_OWNER."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    resp = client.patch(
        f"{PRODUCTS_URL}/{product['id']}",
        json={"title": "Чужое название"},
        headers=other_auth_headers,
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_OWNER"


def test_edit_sku_moderated_product_returns_to_on_moderation(
    client, auth_headers, seed_categories, db
):
    """Редактирование SKU у MODERATED товара → товар переходит в ON_MODERATION."""
    from src.models.product import ProductStatus

    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    sku = _create_sku(client, auth_headers, product["id"])
    _set_product_status(db, product["id"], ProductStatus.MODERATED)

    # Редактируем SKU
    resp = client.patch(
        f"{SKUS_URL}/{sku['id']}",
        json={"price": 99000},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["price"] == 99000

    # Товар перешёл в ON_MODERATION
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    assert product_resp.json()["status"] == "ON_MODERATION"


def test_reserves_preserved_after_sku_edit(
    client, auth_headers, seed_categories, db
):
    """
    При редактировании SKU резервы остаются в силе.
    reserved_quantity не меняется.
    """
    from src.models.product import ProductStatus
    from src.models.sku import SKU

    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    sku = _create_sku(client, auth_headers, product["id"])
    _set_product_status(db, product["id"], ProductStatus.MODERATED)

    # Эмулируем резерв: ставим stock=10, reserved=3
    db_sku = db.query(SKU).filter(SKU.id == uuid.UUID(sku["id"])).first()
    db_sku.stock_quantity = 10
    db_sku.reserved_quantity = 3
    db.commit()

    # Редактируем SKU
    resp = client.patch(
        f"{SKUS_URL}/{sku['id']}",
        json={"name": "250г зерно (обновлено)"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    # Резервы сохранены
    assert resp.json()["reserved_quantity"] == 3
    assert resp.json()["stock_quantity"] == 10
    assert resp.json()["active_quantity"] == 7  # stock - reserved


def test_edit_others_sku_returns_403(
    client, auth_headers, other_auth_headers, seed_categories
):
    """Редактирование чужого SKU → 403 NOT_OWNER."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])
    sku = _create_sku(client, auth_headers, product["id"])

    resp = client.patch(
        f"{SKUS_URL}/{sku['id']}",
        json={"price": 1},
        headers=other_auth_headers,
    )

    assert resp.status_code == 403


def test_edit_created_product_no_status_change(
    client, auth_headers, seed_categories
):
    """Редактирование CREATED товара — статус не меняется (нет побочного эффекта)."""
    product = _create_product(client, auth_headers, seed_categories["mono_id"])

    resp = client.patch(
        f"{PRODUCTS_URL}/{product['id']}",
        json={"title": "Обновлено"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "CREATED"  # не изменился
