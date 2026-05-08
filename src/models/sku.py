"""
Модель SKU — конкретный вариант товара для продажи.
Пример: Кофе «Эфиопия» 250г зерно = один SKU, 1кг молотый = другой.

Quantity model:
  active_quantity — доступно для продажи
  reserved_quantity — зарезервировано в заказах
  on_hand = active + reserved (всё на складе)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)          # цена в копейках
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # себестоимость
    discount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)    # скидка в копейках
    image: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # одиночное фото SKU

    # Количественная модель
    active_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
    characteristics: Mapped[list["SKUCharacteristic"]] = relationship(
        "SKUCharacteristic", back_populates="sku", cascade="all, delete-orphan"
    )


class SKUCharacteristic(Base):
    """Характеристика SKU: Вес = 250г, Помол = Зерно."""
    __tablename__ = "sku_characteristics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)

    sku: Mapped["SKU"] = relationship("SKU", back_populates="characteristics")
