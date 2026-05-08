"""
Модель категории товаров.
Дерево: Напитки → Кофе → Моносорта / Смеси / Декаф
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("categories.id"), nullable=True
    )

    # Связи
    parent: Mapped["Category | None"] = relationship(
        "Category", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(
        "Category", back_populates="parent"
    )
