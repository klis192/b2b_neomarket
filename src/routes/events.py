"""
Эндпоинт для входящих событий от Moderation.
US-B2B-09: POST /api/v1/moderation/events
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.dependencies import require_service_key
from src.database import get_db
from src.schemas.events import ModerationEventRequest
from src.services import event_service

router = APIRouter(prefix="/api/v1/moderation", tags=["Moderation Events"])


@router.post("/events", status_code=204)
def receive_moderation_event(
    data: ModerationEventRequest,
    service: str = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    """
    Приём решения модерации (US-B2B-09).
    MODERATED → одобрен. BLOCKED → soft/hard блокировка.
    Каскад PRODUCT_BLOCKED → B2C при блокировке.
    Идемпотентно по idempotency_key.
    """
    event_service.process_moderation_event(db, data)
    return None
