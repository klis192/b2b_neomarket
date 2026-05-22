"""
Модель товара.
Статусы: CREATED → ON_MODERATION → MODERATED / BLOCKED / HARD_BLOCKED
Soft delete: deleted=True (физически не удаляется).
Поля по спеке neomarket-protocols/b2b/openapi.yaml (ProductResponse).
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Uuid
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

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    seller_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sellers.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), nullable=False, default=ProductStatus.CREATED
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=False
    )

    # Soft delete
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Информация о блокировке (заполняется модерацией, US-B2B-09)
    blocking_reason_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Полный объект причины блокировки {id, title, comment} — для отображения продавцу
    blocking_reason: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Замечания по конкретным полям [{field_name, sku_id, comment}] — для исправления
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
    """Фото товара. ordering определяет порядок. id — в ответе (по спеке)."""
    __tablename__ = "product_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped["Product"] = relationship("Product", back_populates="images")


class ProductCharacteristic(Base):
    """Характеристика товара. id — в ответе (по спеке CharacteristicResponse)."""
    __tablename__ = "product_characteristics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)

    product: Mapped["Product"] = relationship("Product", back_populates="characteristics")
