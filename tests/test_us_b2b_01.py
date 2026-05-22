"""
Тесты для US-B2B-01: Создание карточки товара.
Имена тестов — из контракта.
"""

import uuid

import pytest

URL = "/api/v1/products"


def _valid_product(category_id: str) -> dict:
    """Валидный запрос на создание товара."""
    return {
        "title": "Эфиопия Иргачеффе",
        "description": "Яркий моносорт с нотами жасмина и бергамота",
        "category_id": category_id,
        "images": [
            {"url": "/s3/ethiopia-1.jpg", "ordering": 0},
            {"url": "/s3/ethiopia-2.jpg", "ordering": 1},
        ],
        "characteristics": [
            {"name": "Страна", "value": "Эфиопия"},
            {"name": "Обжарка", "value": "Светлая"},
        ],
    }


def test_create_product_returns_201_with_created_status(
    client, auth_headers, seed_categories
):
    """Успешное создание товара возвращает 201 и статус CREATED."""
    data = _valid_product(seed_categories["mono_id"])
    resp = client.post(URL, json=data, headers=auth_headers)

    assert resp.status_code == 201
    body = resp.json()

    # Основные поля
    assert body["title"] == "Эфиопия Иргачеффе"
    assert body["description"] == "Яркий моносорт с нотами жасмина и бергамота"
    assert body["status"] == "CREATED"
    assert body["deleted"] is False
    assert body["blocking_reason_id"] is None
    assert body["moderator_comment"] is None

    # Обязательные поля по спеке
    assert "id" in body
    assert "seller_id" in body
    assert "category_id" in body
    assert "created_at" in body
    assert "updated_at" in body

    # Категория — плоский UUID
    assert body["category_id"] == seed_categories["mono_id"]

    # Изображения с id
    assert len(body["images"]) == 2
    assert "id" in body["images"][0]
    assert body["images"][0]["url"] == "/s3/ethiopia-1.jpg"

    # Характеристики с id
    assert len(body["characteristics"]) == 2
    assert "id" in body["characteristics"][0]

    # SKU пустой при создании
    assert body["skus"] == []

    # ID — валидный UUID
    uuid.UUID(body["id"])


def test_seller_id_taken_from_jwt(
    client, auth_headers, other_auth_headers, seed_categories
):
    """seller_id берётся из JWT — два продавца создают разные товары."""
    data = _valid_product(seed_categories["mono_id"])

    resp1 = client.post(URL, json=data, headers=auth_headers)
    resp2 = client.post(URL, json=data, headers=other_auth_headers)

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    # Разные seller_id в ответе
    assert resp1.json()["seller_id"] != resp2.json()["seller_id"]


def test_missing_images_returns_400(client, auth_headers, seed_categories):
    """Товар без изображений → 400 (минимум 1 фото по канону)."""
    data = _valid_product(seed_categories["mono_id"])
    data["images"] = []

    resp = client.post(URL, json=data, headers=auth_headers)
    assert resp.status_code == 400


def test_missing_category_returns_400(client, auth_headers):
    """Несуществующая категория → 400."""
    data = {
        "title": "Тестовый товар",
        "description": "Описание",
        "category_id": str(uuid.uuid4()),
        "images": [{"url": "/s3/test.jpg", "ordering": 0}],
    }
    resp = client.post(URL, json=data, headers=auth_headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"


def test_create_product_without_auth_returns_401(client, seed_categories):
    """Запрос без токена → 401."""
    data = _valid_product(seed_categories["mono_id"])
    resp = client.post(URL, json=data)
    assert resp.status_code == 401


def test_create_product_empty_title_returns_400(
    client, auth_headers, seed_categories
):
    """Пустой title → 400."""
    data = _valid_product(seed_categories["mono_id"])
    data["title"] = ""
    resp = client.post(URL, json=data, headers=auth_headers)
    assert resp.status_code == 400


def test_create_product_without_characteristics(
    client, auth_headers, seed_categories
):
    """Характеристики необязательны — товар создаётся без них."""
    data = _valid_product(seed_categories["mono_id"])
    del data["characteristics"]
    resp = client.post(URL, json=data, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["characteristics"] == []


def test_create_product_does_not_send_to_moderation(
    client, auth_headers, seed_categories
):
    """Инвариант: при создании товар НЕ отправляется на модерацию."""
    data = _valid_product(seed_categories["mono_id"])
    resp = client.post(URL, json=data, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "CREATED"


def test_seller_id_in_body_is_ignored(
    client, auth_headers, seed_categories, other_seller_id
):
    """seller_id в body игнорируется — берётся из JWT."""
    data = _valid_product(seed_categories["mono_id"])
    data["seller_id"] = str(other_seller_id)
    resp = client.post(URL, json=data, headers=auth_headers)
    assert resp.status_code == 201
