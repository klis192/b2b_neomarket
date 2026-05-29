"""
Тесты для US-B2B-09: Применение решения модерации.
Имена тестов — из контракта.
"""

import uuid
from datetime import datetime, timezone

import pytest

PRODUCTS_URL = "/api/v1/products"
SKUS_URL = "/api/v1/skus"
MOD_EVENTS_URL = "/api/v1/moderation/events"


def _create_product_on_moderation(client, auth_headers, category_id, db) -> dict:
    """Хелпер: создаёт товар в ON_MODERATION (с SKU)."""
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

    # Статус теперь ON_MODERATION (после первого SKU)
    return product


def test_moderated_event_clears_blocking_data(
    client, auth_headers, mod_service_headers, seed_categories, db
):
    """
    Событие MODERATED → статус MODERATED, blocking_reason очищается.
    """
    from src.models.product import Product

    product = _create_product_on_moderation(
        client, auth_headers, seed_categories["mono_id"], db
    )

    # Сначала заблокируем (чтобы было что очищать)
    client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product["id"],
        "event_type": "BLOCKED",
        "hard_block": False,
        "blocking_reason_id": str(uuid.uuid4()),
        "moderator_comment": "Плохое описание",
        "field_reports": [{"field_name": "description", "comment": "Исправьте"}],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }, headers=mod_service_headers)

    # Теперь одобряем
    resp = client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product["id"],
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }, headers=mod_service_headers)

    assert resp.status_code == 204

    # Проверяем: статус MODERATED, blocking data очищена
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    body = product_resp.json()
    assert body["status"] == "MODERATED"
    assert body["blocking_reason_id"] is None
    assert body["moderator_comment"] is None
    assert body["blocking_reason"] is None
    assert body["field_reports"] == []


def test_blocked_soft_saves_field_reports(
    client, auth_headers, mod_service_headers, seed_categories, db
):
    """
    Событие BLOCKED (hard_block=false) → статус BLOCKED, сохраняет field_reports.
    Каскадное событие PRODUCT_BLOCKED → B2C.
    """
    from src.models.product import Product
    from src.models.outbox import Outbox

    product = _create_product_on_moderation(
        client, auth_headers, seed_categories["mono_id"], db
    )

    reason_id = str(uuid.uuid4())
    resp = client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product["id"],
        "event_type": "BLOCKED",
        "hard_block": False,
        "blocking_reason_id": reason_id,
        "moderator_comment": "Несоответствие фото",
        "field_reports": [
            {"field_name": "description", "sku_id": None, "comment": "Текст скопирован"},
            {"field_name": "images[0]", "sku_id": None, "comment": "Фото другого товара"},
        ],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }, headers=mod_service_headers)

    assert resp.status_code == 204

    # Проверяем: статус BLOCKED, данные блокировки сохранены
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    body = product_resp.json()
    assert body["status"] == "BLOCKED"
    assert body["blocked"] is True
    assert body["blocking_reason_id"] == reason_id
    assert body["moderator_comment"] == "Несоответствие фото"
    assert len(body["field_reports"]) == 2
    assert body["field_reports"][0]["field_name"] == "description"

    # Каскадное событие PRODUCT_BLOCKED → B2C в outbox
    event = db.query(Outbox).filter(Outbox.event_type == "PRODUCT_BLOCKED").first()
    assert event is not None
    assert event.payload["payload"]["product_id"] == product["id"]
    assert event.payload["payload"]["hard_block"] is False


def test_blocked_hard_sets_hard_blocked(
    client, auth_headers, mod_service_headers, seed_categories, db
):
    """
    Событие BLOCKED (hard_block=true) → статус HARD_BLOCKED (терминальный).
    """
    product = _create_product_on_moderation(
        client, auth_headers, seed_categories["mono_id"], db
    )

    resp = client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": product["id"],
        "event_type": "BLOCKED",
        "hard_block": True,
        "blocking_reason_id": str(uuid.uuid4()),
        "moderator_comment": "Контрафакт",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }, headers=mod_service_headers)

    assert resp.status_code == 204

    # Проверяем: HARD_BLOCKED
    product_resp = client.get(
        f"{PRODUCTS_URL}/{product['id']}", headers=auth_headers
    )
    body = product_resp.json()
    assert body["status"] == "HARD_BLOCKED"
    assert body["blocked"] is True


def test_duplicate_event_same_idempotency_key_no_side_effects(
    client, auth_headers, mod_service_headers, seed_categories, db
):
    """
    Идемпотентность: повторное событие с тем же idempotency_key
    не вызывает побочных эффектов (не дублирует outbox записи).
    """
    from src.models.outbox import Outbox

    product = _create_product_on_moderation(
        client, auth_headers, seed_categories["mono_id"], db
    )

    idem_key = str(uuid.uuid4())
    event_data = {
        "idempotency_key": idem_key,
        "product_id": product["id"],
        "event_type": "BLOCKED",
        "hard_block": False,
        "blocking_reason_id": str(uuid.uuid4()),
        "moderator_comment": "Тест идемпотентности",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }

    # Первый раз
    resp1 = client.post(MOD_EVENTS_URL, json=event_data, headers=mod_service_headers)
    assert resp1.status_code == 204

    # Считаем outbox записи
    count_before = db.query(Outbox).filter(Outbox.event_type == "PRODUCT_BLOCKED").count()

    # Повторный с тем же ключом
    resp2 = client.post(MOD_EVENTS_URL, json=event_data, headers=mod_service_headers)
    assert resp2.status_code == 204

    # Outbox не изменился — дубль не создан
    count_after = db.query(Outbox).filter(Outbox.event_type == "PRODUCT_BLOCKED").count()
    assert count_after == count_before


def test_moderation_event_product_not_found_returns_404(
    client, mod_service_headers
):
    """Несуществующий product_id → 404."""
    resp = client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(uuid.uuid4()),
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }, headers=mod_service_headers)

    assert resp.status_code == 404


def test_moderation_event_without_service_key_returns_401(client):
    """Без X-Service-Key → 401."""
    resp = client.post(MOD_EVENTS_URL, json={
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(uuid.uuid4()),
        "event_type": "MODERATED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    })

    assert resp.status_code == 401
