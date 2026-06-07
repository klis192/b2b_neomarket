from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.database import get_db
from src.auth.dependencies import require_service_key
from src.schemas.moderation import ModerationEvent
from src.services.moderation_service import apply_moderation_event

router = APIRouter(prefix="/api/v1/events", tags=["moderation"])


@router.post("/moderation", status_code=200)
def moderation_callback(
    event: ModerationEvent,
    db: Session = Depends(get_db),
    _: bool = Depends(require_service_key),
):
    try:
        apply_moderation_event(db, event)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)}
        )
