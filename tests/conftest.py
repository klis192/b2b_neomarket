import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base, get_db
from src.main import app
from src.models.product import Product, ProductStatus
from src.models.sku import SKU
import uuid
from datetime import datetime


# Тестовая база SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.rollback()
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    return TestClient(app)


@pytest.fixture(scope="function")
def seed_product(db):
    def _create_product(status=ProductStatus.ON_MODERATION, blocking_reason=None):
        product_id = uuid.uuid4()
        category_id = uuid.uuid4()
        product = Product(
            id=product_id,
            title="Test Product",
            description="Test Description",
            seller_id=uuid.uuid4(),
            category_id=category_id,
            status=status,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        if blocking_reason:
            product.blocking_reason = blocking_reason
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    return _create_product


@pytest.fixture(scope="function")
def seed_categories(db):
    return {"mono_id": uuid.uuid4()}


@pytest.fixture(scope="function")
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="function")
def other_seller_id():
    return uuid.uuid4()
