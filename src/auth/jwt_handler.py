"""
Создание и проверка JWT-токенов (access + refresh).
HS256 для dev, RS256 для прода (переключается через ENV).
"""

import uuid
from datetime import datetime, timezone, timedelta

import jwt

from src.config import settings


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """Создаёт access-токен (1 час)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID, role: str) -> tuple[str, uuid.UUID, datetime]:
    """
    Создаёт refresh-токен (30 дней).
    Возвращает (token_string, jti, expires_at) — jti нужен для записи в БД.
    """
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4()
    expires_at = now + timedelta(seconds=settings.refresh_token_ttl)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(jti),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    """
    Декодирует и проверяет подпись токена.
    Кидает jwt.ExpiredSignatureError или jwt.InvalidTokenError при проблемах.
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
