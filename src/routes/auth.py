"""
Эндпоинты авторизации:
  POST /api/v1/auth/register — регистрация продавца
  POST /api/v1/auth/login    — логин
  POST /api/v1/auth/refresh  — обновление токенов
  POST /api/v1/auth/logout   — выход (отзыв refresh)
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.auth.jwt_handler import decode_token
from src.database import get_db
from src.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from src.services import auth_service

import jwt

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """Регистрация нового продавца. Возвращает пару токенов."""
    return auth_service.register_seller(db, data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Логин по email + пароль. Возвращает пару токенов."""
    return auth_service.login_seller(db, data.email, data.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    """Обновление токенов (rotation). Старый refresh → blacklist."""
    return auth_service.refresh_tokens(db, data.refresh_token)


@router.post("/logout", status_code=204)
def logout(
    data: LogoutRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Выход — отзыв refresh-токена.
    Требует access-токен в Authorization и refresh-токен в теле.
    """
    # Проверяем access-токен
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Требуется Bearer токен"},
        )

    try:
        access_claims = decode_token(authorization[7:])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_EXPIRED", "message": "Access-токен истёк"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Невалидный access-токен"},
        )

    auth_service.logout(db, access_claims, data.refresh_token)
    return None
