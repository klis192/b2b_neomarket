"""
Модель SKU — конкретный вариант товара.
Поля по спеке neomarket-protocols/b2b/openapi.yaml (SKUResponse).

Quantity model:
  stock_quantity — всего на складе
  reserved_quantity — зарезервировано в заказах
  active_quantity — доступно к продаже (stock - reserved), вычисляемое
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)              # в копейках
    discount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # скидка в копейках
    cost_price: Mapped[int | None] = mapped_column(Integer, nullable=True)   # себестоимость, nullable
    article: Mapped[str | None] = mapped_column(String(100), nullable=True)  # артикул

    # Количественная модель
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    @property
    def active_quantity(self) -> int:
        """Доступно к продаже = всего на складе - зарезервировано."""
        return self.stock_quantity - self.reserved_quantity

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
    product: Mapped["Product"] = relationship("Product", back_populates="skus")  # noqa: F821
    images: Mapped[list["SKUImage"]] = relationship(
        "SKUImage", back_populates="sku", cascade="all, delete-orphan",
        order_by="SKUImage.ordering",
    )
    characteristics: Mapped[list["SKUCharacteristic"]] = relationship(
        "SKUCharacteristic", back_populates="sku", cascade="all, delete-orphan"
    )


class SKUImage(Base):
    """Фото SKU. id + url + ordering — по спеке SKUImageResponse."""
    __tablename__ = "sku_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sku: Mapped["SKU"] = relationship("SKU", back_populates="images")


class SKUCharacteristic(Base):
    """Характеристика SKU. id в ответе — по спеке CharacteristicResponse."""
    __tablename__ = "sku_characteristics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sku_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)

    sku: Mapped["SKU"] = relationship("SKU", back_populates="characteristics")
