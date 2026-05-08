"""
FastAPI dependencies для авторизации.
- get_current_seller — seller_id из JWT (Bearer token)
- require_service_key — проверка X-Service-Key для межсервисных вызовов
"""

import uuid

import jwt
from fastapi import Depends, Header, HTTPException

from src.auth.jwt_handler import decode_token
from src.config import settings


def get_current_seller(authorization: str | None = Header(default=None)) -> uuid.UUID:
    """
    Извлекает seller_id из JWT в заголовке Authorization.
    seller_id ВСЕГДА из токена, НИКОГДА из body/query — защита от IDOR.
    Возвращает UUID продавца.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Требуется Bearer токен"},
        )

    token = authorization[7:]
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_EXPIRED", "message": "Токен истёк"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Невалидный токен"},
        )

    # Проверяем роль — только seller может работать с B2B
    if claims.get("role") != "seller":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "Доступ только для продавцов"},
        )

    return uuid.UUID(claims["sub"])


def require_service_key(x_service_key: str = Header(...)) -> str:
    """
    Проверяет X-Service-Key для межсервисных вызовов.
    Принимает ключи от Moderation и B2C.
    """
    valid_keys = {
        settings.mod_to_b2b_key: "moderation",
        settings.b2c_to_b2b_key: "b2c",
    }

    if x_service_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Невалидный X-Service-Key"},
        )

    return valid_keys[x_service_key]


def get_optional_seller(
    authorization: str | None = Header(default=None),
) -> uuid.UUID | None:
    """
    Опциональная авторизация — для эндпоинтов, которые работают
    и с JWT (seller), и с X-Service-Key (межсервисный).
    Возвращает seller_id или None.
    """
    if authorization is None or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_seller(authorization)
    except HTTPException:
        return None
