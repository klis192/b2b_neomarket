"""Тесты авторизации — register, login, refresh, logout."""

import pytest


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"

VALID_SELLER = {
    "email": "seller@example.com",
    "password": "SecurePass123",
    "company_name": "ООО Кофе",
    "inn": "7707083893",
    "first_name": "Иван",
    "last_name": "Петров",
}


def test_register_returns_201_with_tokens(client):
    """Успешная регистрация возвращает 201 и пару токенов."""
    resp = client.post(REGISTER_URL, json=VALID_SELLER)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 3600


def test_register_duplicate_email_returns_409(client):
    """Повторная регистрация с тем же email → 409."""
    client.post(REGISTER_URL, json=VALID_SELLER)
    resp = client.post(REGISTER_URL, json=VALID_SELLER)
    assert resp.status_code == 409
    assert resp.json()["code"] == "EMAIL_ALREADY_EXISTS"


def test_register_duplicate_inn_returns_409(client):
    """Повторная регистрация с тем же ИНН → 409."""
    client.post(REGISTER_URL, json=VALID_SELLER)
    other = {**VALID_SELLER, "email": "other@example.com"}
    resp = client.post(REGISTER_URL, json=other)
    assert resp.status_code == 409
    assert resp.json()["code"] == "INN_ALREADY_EXISTS"


def test_register_weak_password_returns_400(client):
    """Пароль без цифры → 400."""
    data = {**VALID_SELLER, "password": "NoDigitsHere"}
    resp = client.post(REGISTER_URL, json=data)
    assert resp.status_code == 400


def test_login_returns_tokens(client):
    """Успешный логин возвращает токены."""
    client.post(REGISTER_URL, json=VALID_SELLER)
    resp = client.post(LOGIN_URL, json={
        "email": VALID_SELLER["email"],
        "password": VALID_SELLER["password"],
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password_returns_401(client):
    """Неверный пароль → 401 INVALID_CREDENTIALS."""
    client.post(REGISTER_URL, json=VALID_SELLER)
    resp = client.post(LOGIN_URL, json={
        "email": VALID_SELLER["email"],
        "password": "WrongPass123",
    })
    assert resp.status_code == 401
    assert resp.json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_returns_401(client):
    """Несуществующий email → 401 (не раскрываем что именно не так)."""
    resp = client.post(LOGIN_URL, json={
        "email": "unknown@example.com",
        "password": "Whatever123",
    })
    assert resp.status_code == 401


def test_refresh_returns_new_tokens(client):
    """Refresh возвращает новую пару токенов."""
    reg = client.post(REGISTER_URL, json=VALID_SELLER).json()
    resp = client.post(REFRESH_URL, json={
        "refresh_token": reg["refresh_token"],
    })
    assert resp.status_code == 200
    data = resp.json()
    # Новые токены должны отличаться от старых
    assert data["access_token"] != reg["access_token"]
    assert data["refresh_token"] != reg["refresh_token"]


def test_refresh_reuse_returns_401(client):
    """Повторное использование refresh → 401 TOKEN_REVOKED."""
    reg = client.post(REGISTER_URL, json=VALID_SELLER).json()
    old_refresh = reg["refresh_token"]

    # Первый refresh — OK
    client.post(REFRESH_URL, json={"refresh_token": old_refresh})

    # Второй с тем же токеном — revoked
    resp = client.post(REFRESH_URL, json={"refresh_token": old_refresh})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_REVOKED"


def test_logout_revokes_refresh(client):
    """После logout refresh перестаёт работать."""
    reg = client.post(REGISTER_URL, json=VALID_SELLER).json()

    # Logout
    resp = client.post(
        LOGOUT_URL,
        json={"refresh_token": reg["refresh_token"]},
        headers={"Authorization": f"Bearer {reg['access_token']}"},
    )
    assert resp.status_code == 204

    # Refresh после logout → revoked
    resp = client.post(REFRESH_URL, json={"refresh_token": reg["refresh_token"]})
    assert resp.status_code == 401
