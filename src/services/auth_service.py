"""
Бизнес-логика авторизации: регистрация, логин, refresh, logout.
Пароль хэшируется через bcrypt. Refresh-токены с rotation + blacklist.
"""

import uuid
from datetime import datetime, timezone

import bcrypt
import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.config import settings
from src.models.user import RefreshBlacklist, RefreshToken, Seller
from src.schemas.auth import RegisterRequest


def hash_password(password: str) -> str:
    """Хэширует пароль через bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет пароль против bcrypt-хэша."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _generate_tokens(db: Session, user_id: uuid.UUID, role: str) -> dict:
    """Генерирует пару access + refresh, записывает refresh в БД."""
    access = create_access_token(user_id, role)
    refresh, jti, expires_at = create_refresh_token(user_id, role)

    # Сохраняем refresh-токен в БД
    db.add(RefreshToken(
        jti=jti,
        user_id=user_id,
        issued_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    ))
    db.commit()

    return {
        "user_id": str(user_id),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": settings.access_token_ttl,
    }


def register_seller(db: Session, data: RegisterRequest) -> dict:
    """
    Регистрация нового продавца.
    Проверяет уникальность email и ИНН, хэширует пароль, создаёт токены.
    """
    # Проверяем уникальность email
    if db.query(Seller).filter(Seller.email == data.email).first():
        raise HTTPException(
            status_code=409,
            detail={"code": "EMAIL_ALREADY_EXISTS", "message": "Email уже зарегистрирован"},
        )

    # Проверяем уникальность ИНН
    if db.query(Seller).filter(Seller.inn == data.inn).first():
        raise HTTPException(
            status_code=409,
            detail={"code": "INN_ALREADY_EXISTS", "message": "ИНН уже зарегистрирован"},
        )

    # Создаём продавца
    seller = Seller(
        email=data.email,
        password_hash=hash_password(data.password),
        company_name=data.company_name,
        inn=data.inn,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
    )
    db.add(seller)
    db.flush()  # получаем seller.id

    return _generate_tokens(db, seller.id, seller.role)


def login_seller(db: Session, email: str, password: str) -> dict:
    """
    Логин продавца.
    Не раскрываем что именно не так (email или пароль) — защита от перебора.
    """
    seller = db.query(Seller).filter(Seller.email == email.lower().strip()).first()

    # Один код ошибки для «нет email» и «неверный пароль»
    if not seller or not verify_password(password, seller.password_hash):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Неверный email или пароль"},
        )

    if not seller.is_active:
        raise HTTPException(
            status_code=403,
            detail={"code": "USER_BLOCKED", "message": "Пользователь заблокирован"},
        )

    return _generate_tokens(db, seller.id, seller.role)


def refresh_tokens(db: Session, refresh_token_str: str) -> dict:
    """
    Обновление токенов (rotation + blacklist).
    Старый refresh уходит в blacklist, выдаётся новая пара.
    """
    # Декодируем refresh-токен
    try:
        claims = decode_token(refresh_token_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_EXPIRED", "message": "Refresh-токен истёк"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Невалидный refresh-токен"},
        )

    old_jti = uuid.UUID(claims["jti"])

    # Проверяем blacklist — если токен уже использован, значит утечка
    if db.query(RefreshBlacklist).filter(RefreshBlacklist.jti == old_jti).first():
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_REVOKED", "message": "Токен уже был отозван"},
        )

    # Проверяем что токен известен (есть в refresh_tokens)
    known_token = db.query(RefreshToken).filter(RefreshToken.jti == old_jti).first()
    if not known_token:
        raise HTTPException(
            status_code=401,
            detail={"code": "TOKEN_REVOKED", "message": "Токен не найден"},
        )

    # Rotation: старый → в blacklist, удаляем из активных
    db.add(RefreshBlacklist(
        jti=old_jti,
        expires_at=known_token.expires_at,
    ))
    db.delete(known_token)
    db.flush()

    # Выдаём новую пару
    user_id = uuid.UUID(claims["sub"])
    role = claims["role"]
    return _generate_tokens(db, user_id, role)


def logout(db: Session, access_claims: dict, refresh_token_str: str) -> None:
    """
    Logout — отзываем refresh-токен.
    Проверяем что sub в refresh совпадает с sub в access.
    """
    try:
        refresh_claims = decode_token(refresh_token_str)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Невалидный refresh-токен"},
        )

    # Проверяем что это один и тот же пользователь
    if refresh_claims["sub"] != access_claims["sub"]:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Токены принадлежат разным пользователям"},
        )

    jti = uuid.UUID(refresh_claims["jti"])
    expires_at = datetime.fromtimestamp(refresh_claims["exp"], tz=timezone.utc)

    # Добавляем в blacklist (если ещё не там)
    if not db.query(RefreshBlacklist).filter(RefreshBlacklist.jti == jti).first():
        db.add(RefreshBlacklist(jti=jti, expires_at=expires_at))

    # Удаляем из активных (если есть)
    active = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if active:
        db.delete(active)

    db.commit()
