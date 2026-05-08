"""
Фикстуры для pytest.
Тестовая БД: SQLite in-memory (быстро, изолированно).
"""

import os
import uuid

# Задаём тестовый URL ДО импорта приложения
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.models.category import Category
from src.auth.jwt_handler import create_access_token

# Тестовая БД — SQLite in-memory
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# UUID не поддерживается в SQLite нативно — включаем через CHAR(32)
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def db():
    """Создаёт чистую БД для каждого теста."""
    Base.metadata.create_all(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """FastAPI test client с подменённой БД."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_categories(db):
    """Создаёт дерево категорий для тестов. Возвращает dict с id."""
    root = Category(name="Напитки")
    db.add(root)
    db.flush()

    coffee = Category(name="Кофе", parent_id=root.id)
    db.add(coffee)
    db.flush()

    mono = Category(name="Моносорта", parent_id=coffee.id)
    db.add(mono)
    db.flush()
    db.commit()

    return {
        "root_id": str(root.id),
        "coffee_id": str(coffee.id),
        "mono_id": str(mono.id),
    }


@pytest.fixture
def seller_id(db) -> uuid.UUID:
    """Создаёт продавца в тестовой БД и возвращает его UUID."""
    from src.models.user import Seller
    _id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    seller = Seller(
        id=_id, email="seller1@test.com", password_hash="fake",
        company_name="Test Co", inn="1234567890",
        first_name="Test", last_name="Seller",
    )
    db.add(seller)
    db.commit()
    return _id


@pytest.fixture
def other_seller_id(db) -> uuid.UUID:
    """Создаёт второго продавца — для тестов на ownership."""
    from src.models.user import Seller
    _id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    seller = Seller(
        id=_id, email="seller2@test.com", password_hash="fake",
        company_name="Other Co", inn="0987654321",
        first_name="Other", last_name="Seller",
    )
    db.add(seller)
    db.commit()
    return _id


@pytest.fixture
def auth_headers(seller_id) -> dict:
    """Заголовки с JWT для авторизованного продавца."""
    token = create_access_token(seller_id, "seller")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_auth_headers(other_seller_id) -> dict:
    """Заголовки для другого продавца."""
    token = create_access_token(other_seller_id, "seller")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def service_headers() -> dict:
    """Заголовки для межсервисных вызовов (X-Service-Key от B2C)."""
    from src.config import settings
    return {"X-Service-Key": settings.b2c_to_b2b_key}


@pytest.fixture
def mod_service_headers() -> dict:
    """Заголовки для вызовов от Moderation."""
    from src.config import settings
    return {"X-Service-Key": settings.mod_to_b2b_key}
