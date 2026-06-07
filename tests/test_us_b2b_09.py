import uuid
import pytest
from fastapi.testclient import TestClient


def test_moderated_clears_blocking_data(client, db, seed_product):
    product = seed_product(status="BLOCKED", blocking_reason={"id": "test"})
    event = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product.id),
        "status": "MODERATED"
    }
    resp = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    print("Response status:", resp.status_code)
    print("Response body:", resp.text)
    assert resp.status_code == 200
    db.refresh(product)
    assert product.status.value == "MODERATED"
    assert product.blocking_reason is None


def test_blocked_soft_saves_field_reports(client, db, seed_product):
    product = seed_product(status="ON_MODERATION")
    event = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product.id),
        "status": "BLOCKED",
        "hard_block": False,
        "blocking_reason": {"id": str(uuid.uuid4()), "title": "test", "comment": "test"},
        "field_reports": [{"field_name": "title", "comment": "bad title"}]
    }
    resp = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    print("Response status:", resp.status_code)
    print("Response body:", resp.text)
    assert resp.status_code == 200
    db.refresh(product)
    assert product.status.value == "BLOCKED"
    assert product.blocking_reason is not None


def test_blocked_hard_sets_terminal_status(client, db, seed_product):
    product = seed_product(status="ON_MODERATION")
    event = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product.id),
        "status": "BLOCKED",
        "hard_block": True,
        "blocking_reason": {"id": str(uuid.uuid4()), "title": "test", "comment": "test"},
    }
    resp = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    print("Response status:", resp.status_code)
    print("Response body:", resp.text)
    assert resp.status_code == 200
    db.refresh(product)
    assert product.status.value == "HARD_BLOCKED"


def test_duplicate_event_ignored(client, db, seed_product):
    product = seed_product(status="ON_MODERATION")
    idem_key = str(uuid.uuid4())
    event = {
        "idempotency_key": idem_key,
        "product_id": str(product.id),
        "status": "MODERATED"
    }
    resp1 = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    resp2 = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    assert resp1.status_code == resp2.status_code == 200
    from src.models.processed_event import ProcessedEvent
    count = db.query(ProcessedEvent).filter(ProcessedEvent.idempotency_key == idem_key).count()
    assert count == 1


def test_product_not_found_returns_404(client):
    event = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(uuid.uuid4()),
        "status": "MODERATED"
    }
    resp = client.post(
        "/api/v1/events/moderation",
        json=event,
        headers={"X-Service-Key": "secret-mod-to-b2b"}
    )
    print("Response status:", resp.status_code)
    print("Response body:", resp.text)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
