"""
Тесты для US-B2B-08: Резервирование и снятие резерва SKU.
Имена тестов — из контракта.
"""

import uuid

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
INVOICES_URL = "/api/v1/invoices"
RESERVE_URL = "/api/v1/inventory/reserve"
UNRESERVE_URL = "/api/v1/inventory/unreserve"


def _create_sku_with_stock(client, auth_headers, service_headers, category_id, db, stock=10):
    """Хелпер: создаёт MODERATED товар + SKU со стоком."""
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

    # Накладная + приёмка → stock (пропускаем если stock=0)
    if stock > 0:
        inv = client.post(INVOICES_URL, json={
            "items": [{"sku_id": sku["id"], "quantity": stock}],
        }, headers=auth_headers).json()
        client.post(f"{INVOICES_URL}/{inv['id']}/accept")

    return product, sku


def test_reserve_all_skus_succeeds(
    client, auth_headers, service_headers, seed_categories, db
):
    """Успешное резервирование всех SKU → 200 RESERVED."""
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=10
    )

    resp = client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RESERVED"
    assert "reserved_at" in body

    # Проверяем в БД: stock=10, reserved=3, active=7
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.stock_quantity == 10
    assert db_sku.reserved_quantity == 3
    assert db_sku.active_quantity == 7


def test_partial_insufficient_stock_returns_409_all_rollback(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    All-or-nothing: если один SKU не проходит — вся операция отклоняется.
    Ничего не резервируется.
    """
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=5
    )

    resp = client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": sku["id"], "quantity": 100}],  # больше чем есть
    }, headers=service_headers)

    assert resp.status_code == 409
    body = resp.json()
    assert body["reserved"] is False
    assert len(body["failed_items"]) == 1
    assert body["failed_items"][0]["reason"] == "INSUFFICIENT_STOCK"

    # Ничего не зарезервировано
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 0


def test_idempotent_reserve_returns_200_without_double_deduction(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    Идемпотентность: повторный запрос с тем же idempotency_key
    возвращает 200 без повторного резервирования.
    """
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=10
    )

    idem_key = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    payload = {
        "idempotency_key": idem_key,
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }

    # Первый запрос — резервируем
    resp1 = client.post(RESERVE_URL, json=payload, headers=service_headers)
    assert resp1.status_code == 200

    # Повторный с тем же ключом — идемпотентный ответ
    resp2 = client.post(RESERVE_URL, json=payload, headers=service_headers)
    assert resp2.status_code == 200
    assert resp2.json() == resp1.json()

    # В БД по-прежнему reserved=3 (не 6)
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 3


def test_reserve_out_of_stock_returns_409(
    client, auth_headers, service_headers, seed_categories, db
):
    """active_quantity == 0 → 409 OUT_OF_STOCK."""
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=0
    )

    resp = client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": sku["id"], "quantity": 1}],
    }, headers=service_headers)

    assert resp.status_code == 409
    assert resp.json()["failed_items"][0]["reason"] == "OUT_OF_STOCK"


def test_reserve_sends_sku_out_of_stock_event(
    client, auth_headers, service_headers, seed_categories, db
):
    """Если active_quantity стал 0 после reserve → событие SKU_OUT_OF_STOCK."""
    from src.models.outbox import Outbox

    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=5
    )

    # Резервируем ВСЁ — active станет 0
    resp = client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": sku["id"], "quantity": 5}],
    }, headers=service_headers)

    assert resp.status_code == 200

    # Проверяем событие SKU_OUT_OF_STOCK
    event = db.query(Outbox).filter(Outbox.event_type == "SKU_OUT_OF_STOCK").first()
    assert event is not None
    assert event.payload["payload"]["sku_id"] == sku["id"]


def test_unreserve_restores_active_quantity(
    client, auth_headers, service_headers, seed_categories, db
):
    """Unreserve возвращает остатки: active += N, reserved -= N."""
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=10
    )

    order_id = str(uuid.uuid4())

    # Резервируем 3
    client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    # Снимаем резерв
    resp = client.post(UNRESERVE_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "UNRESERVED"

    # В БД: stock=10, reserved=0, active=10
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 0
    assert db_sku.active_quantity == 10


def test_reserve_without_service_key_returns_401(client):
    """Без X-Service-Key → 401."""
    resp = client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": str(uuid.uuid4()),
        "items": [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    })
    assert resp.status_code == 401


def test_idempotent_unreserve_returns_200_without_double_deduction(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    Идемпотентность unreserve: повторный вызов с тем же order_id
    не вычитает reserved_quantity дважды.
    """
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=10
    )

    order_id = str(uuid.uuid4())

    # Резервируем
    client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    # Первый unreserve — OK
    resp1 = client.post(UNRESERVE_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "UNRESERVED"

    # Повторный unreserve — идемпотентный (не вычитает дважды)
    resp2 = client.post(UNRESERVE_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "UNRESERVED"

    # В БД reserved=0 (не -3)
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 0


def test_unreserve_uses_stored_quantities(
    client, auth_headers, service_headers, seed_categories, db
):
    """
    Unreserve берёт количества из сохранённой операции (не из запроса).
    Защита от подмены quantity клиентом.
    """
    product, sku = _create_sku_with_stock(
        client, auth_headers, service_headers, seed_categories["mono_id"], db, stock=10
    )

    order_id = str(uuid.uuid4())

    # Резервируем 3
    client.post(RESERVE_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 3}],
    }, headers=service_headers)

    # Unreserve с quantity=100 (попытка подмены) — снимет только 3
    resp = client.post(UNRESERVE_URL, json={
        "order_id": order_id,
        "items": [{"sku_id": sku["id"], "quantity": 100}],
    }, headers=service_headers)
    assert resp.status_code == 200

    # В БД reserved=0 (не -97)
    from src.models.sku import SKU as SKUModel
    db_sku = db.query(SKUModel).filter(SKUModel.id == uuid.UUID(sku["id"])).first()
    assert db_sku.reserved_quantity == 0
    assert db_sku.active_quantity == 10
