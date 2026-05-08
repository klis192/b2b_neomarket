"""
Модель товара.
Статусы: CREATED → ON_MODERATION → MODERATED / BLOCKED / HARD_BLOCKED
Soft delete: deleted=True (физически не удаляется).
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy import Uuid
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class ProductStatus(str, enum.Enum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), nullable=False, default=ProductStatus.CREATED
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False
    )

    # Soft delete
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Информация о блокировке (заполняется модерацией)
    blocking_reason: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    field_reports: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Метаданные
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Связи
    category: Mapped["Category"] = relationship("Category")  # noqa: F821
    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan",
        order_by="ProductImage.ordering",
    )
    characteristics: Mapped[list["ProductCharacteristic"]] = relationship(
        "ProductCharacteristic", back_populates="product", cascade="all, delete-orphan"
    )
    skus: Mapped[list["SKU"]] = relationship(  # noqa: F821
        "SKU", back_populates="product", cascade="all, delete-orphan"
    )


class ProductImage(Base):
    """Фото товара. ordering определяет порядок показа."""
    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped["Product"] = relationship("Product", back_populates="images")


class ProductCharacteristic(Base):
    """Характеристика товара: Страна = Эфиопия, Обжарка = Средняя."""
    __tablename__ = "product_characteristics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="characteristics")
