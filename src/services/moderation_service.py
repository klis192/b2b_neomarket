import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException

from src.models.product import Product, ProductStatus
from src.models.processed_event import ProcessedEvent
from src.models.outbox import Outbox
from src.schemas.moderation import ModerationEvent, ModerationStatus
from src.config import settings


def apply_moderation_event(db: Session, event: ModerationEvent) -> None:
    # 1. Идемпотентность
    existing = db.query(ProcessedEvent).filter(
        ProcessedEvent.idempotency_key == str(event.idempotency_key)
    ).first()
    if existing:
        return
    
    # 2. Найти товар
    product = db.query(Product).filter(Product.id == event.product_id).first()
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"}
        )
    
    sku_ids = [str(sku.id) for sku in product.skus]
    now = datetime.now(timezone.utc).isoformat()
    
    # 3. Применить решение
    if event.status == ModerationStatus.MODERATED:
        product.status = ProductStatus.MODERATED
        product.blocking_reason_id = None
        product.moderator_comment = None
        product.blocking_reason = None
        product.field_reports = None
        
    else:  # BLOCKED
        if event.hard_block:
            product.status = ProductStatus.HARD_BLOCKED
        else:
            product.status = ProductStatus.BLOCKED
        
        if event.blocking_reason:
            product.blocking_reason = event.blocking_reason.model_dump()
            product.blocking_reason_id = str(event.blocking_reason.id)  # UUID → str
        if event.field_reports:
            product.field_reports = [fr.model_dump() for fr in event.field_reports]
        
        # Каскад в B2C
        db.add(Outbox(
            idempotency_key=uuid.uuid4(),
            event_type="PRODUCT_BLOCKED",
            payload={
                "event": "PRODUCT_BLOCKED",
                "product_id": str(event.product_id),
                "sku_ids": sku_ids,
                "date": now,
                "occurred_at": now,
                "payload": {
                    "product_id": str(event.product_id),
                    "sku_ids": sku_ids,
                },
            },
            target_url=f"{settings.b2c_url}/api/v1/events/product",
        ))
    
    # 4. Записать идемпотентность (конвертируем UUID в строки)
    db.add(ProcessedEvent(
        id=uuid.uuid4().hex,
        sender_service="moderation",
        idempotency_key=str(event.idempotency_key),  # UUID → str
        product_id=str(event.product_id)             # UUID → str
    ))
    db.commit()
