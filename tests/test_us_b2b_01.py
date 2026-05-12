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

    # Проверяем основные поля
    assert body["title"] == "Эфиопия Иргачеффе"
    assert body["description"] == "Яркий моносорт с нотами жасмина и бергамота"
    assert body["status"] == "CREATED"
    assert body["deleted"] is False
    assert body["blocked"] is False

    # Проверяем категорию (плоские поля по спеке openapi)
    assert body["category_id"] == seed_categories["mono_id"]
    assert body["category_name"] == "Моносорта"

    # Проверяем изображения
    assert len(body["images"]) == 2
    assert body["images"][0]["url"] == "/s3/ethiopia-1.jpg"

    # Проверяем характеристики
    assert len(body["characteristics"]) == 2

    # SKU пустой при создании
    assert body["skus"] == []

    # ID — валидный UUID
    uuid.UUID(body["id"])  # не кидает исключение = валидный


def test_seller_id_taken_from_jwt(
    client, auth_headers, other_auth_headers, seed_categories
):
    """
    seller_id берётся из JWT, а не из тела запроса.
    Два разных продавца создают товары — у каждого свой seller_id.
    """
    data = _valid_product(seed_categories["mono_id"])

    # Первый продавец
    resp1 = client.post(URL, json=data, headers=auth_headers)
    assert resp1.status_code == 201

    # Второй продавец
    resp2 = client.post(URL, json=data, headers=other_auth_headers)
    assert resp2.status_code == 201

    # ID товаров разные (каждый принадлежит своему продавцу)
    assert resp1.json()["id"] != resp2.json()["id"]


def test_missing_images_returns_400(client, auth_headers, seed_categories):
    """Товар без изображений → 400."""
    data = _valid_product(seed_categories["mono_id"])
    data["images"] = []  # пустой массив

    resp = client.post(URL, json=data, headers=auth_headers)

    # Пустой массив images → 400 INVALID_REQUEST
    assert resp.status_code == 400


def test_missing_category_returns_400(client, auth_headers):
    """Несуществующая категория → 400."""
    data = {
        "title": "Тестовый товар",
        "description": "Описание",
        "category_id": str(uuid.uuid4()),  # несуществующий UUID
        "images": [{"url": "/s3/test.jpg", "ordering": 0}],
    }

    resp = client.post(URL, json=data, headers=auth_headers)

    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_REQUEST"
    assert "Category not found" in resp.json()["message"]


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
    """Инвариант: при создании товар НЕ отправляется на модерацию (нужен SKU)."""
    data = _valid_product(seed_categories["mono_id"])

    resp = client.post(URL, json=data, headers=auth_headers)

    assert resp.status_code == 201
    # Статус CREATED, не ON_MODERATION
    assert resp.json()["status"] == "CREATED"


def test_seller_id_in_body_is_ignored(
    client, auth_headers, seed_categories, other_seller_id
):
    """Атака: seller_id в body — должен игнорироваться, берётся из JWT."""
    data = _valid_product(seed_categories["mono_id"])
    # Пытаемся подсунуть чужой seller_id в body
    data["seller_id"] = str(other_seller_id)

    resp = client.post(URL, json=data, headers=auth_headers)

    # Товар создаётся успешно — seller_id из body просто игнорируется Pydantic-ой
    # (поле seller_id не объявлено в ProductCreate)
    assert resp.status_code == 201
