"""
Pydantic-схемы для авторизации.
Регистрация, логин, refresh, ответ с токенами.
"""

import re

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    """
    Регистрация продавца.
    Пароль: 8+ символов, минимум 1 цифра и 1 буква.
    ИНН: 10 или 12 цифр.
    """
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8)
    company_name: str = Field(..., min_length=1, max_length=255)
    inn: str = Field(..., min_length=10, max_length=12)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(default=None)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Простая проверка формата email
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Невалидный email")
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-zА-Яа-яЁё]", v):
            raise ValueError("Пароль должен содержать хотя бы одну букву")
        if not re.search(r"\d", v):
            raise ValueError("Пароль должен содержать хотя бы одну цифру")
        return v

    @field_validator("inn")
    @classmethod
    def validate_inn(cls, v: str) -> str:
        if not re.match(r"^\d{10}$|^\d{12}$", v):
            raise ValueError("ИНН должен содержать 10 или 12 цифр")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # E.164: +7XXXXXXXXXX
        if not re.match(r"^\+\d{10,15}$", v):
            raise ValueError("Телефон должен быть в формате E.164 (например +79001234567)")
        return v


class LoginRequest(BaseModel):
    """Логин по email + пароль."""
    email: str
    password: str


class RefreshRequest(BaseModel):
    """Обновление токенов."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout — передаём refresh_token для отзыва."""
    refresh_token: str


class TokenResponse(BaseModel):
    """Ответ с парой токенов (register, login, refresh)."""
    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
