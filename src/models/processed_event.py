import uuid
from datetime import datetime, timezone
from sqlalchemy import Uuid, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from src.database import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = {"extend_existing": True}
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    sender_service: Mapped[str] = mapped_column(String(50), nullable=True)  # теперь nullable=True
    idempotency_key: Mapped[str] = mapped_column(String(32), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    product_id: Mapped[str] = mapped_column(String(32), nullable=False)