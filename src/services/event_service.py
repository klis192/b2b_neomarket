"""
Бизнес-логика обработки входящих событий от Moderation.
US-B2B-09: применение решения модерации.
Три пути: MODERATED, BLOCKED (soft), BLOCKED (hard → HARD_BLOCKED).
Каскадное событие PRODUCT_BLOCKED → B2C при блокировке.
Идемпотентность по (sender_service, idempotency_key).
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models.product import Product, ProductStatus
from src.models.outbox import Outbox, ProcessedEvent
from src.config import settings
from src.schemas.events import ModerationEventRequest


def process_moderation_event(
    db: Session,
    data: ModerationEventRequest,
) -> None:
    """
    Обработка решения модерации (B2B-9).
    MODERATED → одобрен. BLOCKED + hard_block=false → мягкая блокировка.
    BLOCKED + hard_block=true → HARD_BLOCKED (терминальный).
    Каскад PRODUCT_BLOCKED → B2C при любой блокировке.
    """
    # Идемпотентность — если событие уже обработано, возвращаем 204 без side-effects
    existing = db.query(ProcessedEvent).filter(
        ProcessedEvent.sender_service == "moderation",
        ProcessedEvent.idempotency_key == data.idempotency_key,
    ).first()
    if existing:
        return  # дубликат — молча игнорируем

    # Валидация event_type
    if data.event_type not in ("MODERATED", "BLOCKED"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": f"Unknown event_type: {data.event_type}"},
        )

    # Находим товар
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Product not found"},
        )

    now = datetime.now(timezone.utc)

    if data.event_type == "MODERATED":
        # Одобрен модератором
        product.status = ProductStatus.MODERATED
        # Очищаем данные предыдущей блокировки (если были)
        product.blocking_reason_id = None
        product.moderator_comment = None
        product.blocking_reason = None
        product.field_reports = None

    elif data.event_type == "BLOCKED":
        if data.hard_block:
            # Жёсткая блокировка — терминальный статус
            product.status = ProductStatus.HARD_BLOCKED
        else:
            # Мягкая блокировка — продавец может исправить
            product.status = ProductStatus.BLOCKED

        # Сохраняем данные блокировки для отображения продавцу
        product.blocking_reason_id = data.blocking_reason_id
        product.moderator_comment = data.moderator_comment

        # Полный объект blocking_reason (канон B2B-5)
        if data.blocking_reason_id:
            product.blocking_reason = {
                "id": str(data.blocking_reason_id),
                "title": data.moderator_comment or "Товар заблокирован",
                "comment": data.moderator_comment or "",
            }

        # Замечания по полям
        if data.field_reports:
            product.field_reports = [
                {
                    "field_name": fr.field_name,
                    "sku_id": str(fr.sku_id) if fr.sku_id else None,
                    "comment": fr.comment,
                }
                for fr in data.field_reports
            ]
        else:
            product.field_reports = None

        # Каскадное событие PRODUCT_BLOCKED → B2C
        sku_ids = [str(sku.id) for sku in product.skus]
        idem_key = uuid.uuid5(uuid.NAMESPACE_URL, f"{product.id}:PRODUCT_BLOCKED:{data.idempotency_key}")
        db.add(Outbox(
            idempotency_key=idem_key,
            event_type="PRODUCT_BLOCKED",
            payload={
                "event_type": "PRODUCT_BLOCKED",
                "idempotency_key": str(idem_key),
                "occurred_at": now.isoformat(),
                "payload": {
                    "product_id": str(product.id),
                    "sku_ids": sku_ids,
                    "hard_block": data.hard_block,
                },
            },
            target_url=f"{settings.b2c_url}/api/v1/events/product",
        ))

    # Записываем обработку для идемпотентности
    db.add(ProcessedEvent(
        sender_service="moderation",
        idempotency_key=data.idempotency_key,
        response_cached={"status": "processed"},
    ))

    db.commit()
