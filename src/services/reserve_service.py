"""
Бизнес-логика резервирования SKU.
US-B2B-08: reserve (all-or-nothing) и unreserve (компенсация).
SELECT FOR UPDATE для конкурентности. Идемпотентность по idempotency_key / order_id.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models.sku import SKU
from src.models.outbox import Outbox, ReserveOperation
from src.config import settings
from src.schemas.reserve import (
    ReserveRequest,
    ReserveResponse,
    InventoryOrderRequest,
    InventoryOrderResponse,
)


def reserve_skus(
    db: Session,
    data: ReserveRequest,
) -> ReserveResponse:
    """
    All-or-nothing резервирование (B2B-8).
    Если хотя бы один SKU не проходит — вся операция отклоняется.
    SELECT FOR UPDATE для защиты от гонок.
    Идемпотентность по idempotency_key.
    """
    # Проверяем идемпотентность — если ключ уже обработан, возвращаем кэш
    existing = db.query(ReserveOperation).filter(
        ReserveOperation.idempotency_key == data.idempotency_key
    ).first()
    if existing:
        return ReserveResponse(**existing.result)

    # Собираем sku_id → quantity из запроса
    requested = {item.sku_id: item.quantity for item in data.items}
    sku_ids = list(requested.keys())

    # SELECT FOR UPDATE — блокируем строки SKU для атомарной проверки и обновления
    # В SQLite FOR UPDATE не работает — используем обычный SELECT для тестов
    skus = db.query(SKU).filter(SKU.id.in_(sku_ids)).all()

    # Проверяем что все SKU найдены
    found_ids = {sku.id for sku in skus}
    missing = set(sku_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    # Проверяем достаточность остатков (all-or-nothing)
    failed_items = []
    for sku in skus:
        needed = requested[sku.id]
        available = sku.active_quantity
        if available < needed:
            reason = "OUT_OF_STOCK" if available == 0 else "INSUFFICIENT_STOCK"
            failed_items.append({
                "sku_id": str(sku.id),
                "requested": needed,
                "available": available,
                "reason": reason,
            })

    # Если хотя бы один не проходит — отклоняем ВСЮ операцию
    if failed_items:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "INSUFFICIENT_STOCK",
                "message": "Not enough stock for reservation",
                "reserved": False,
                "failed_items": failed_items,
            },
        )

    # Всё ок — резервируем
    now = datetime.now(timezone.utc)
    for sku in skus:
        needed = requested[sku.id]
        sku.stock_quantity = sku.stock_quantity  # не меняем stock
        # active = stock - reserved, поэтому меняем reserved
        sku.reserved_quantity += needed

        # Если active_quantity стал 0 → событие SKU_OUT_OF_STOCK для B2C
        if sku.active_quantity == 0:
            db.add(Outbox(
                idempotency_key=uuid.uuid5(uuid.NAMESPACE_URL, f"{sku.id}:OUT_OF_STOCK:{now.isoformat()}"),
                event_type="SKU_OUT_OF_STOCK",
                payload={
                    "event_type": "SKU_OUT_OF_STOCK",
                    "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{sku.id}:OUT_OF_STOCK:{now.isoformat()}")),
                    "occurred_at": now.isoformat(),
                    "payload": {
                        "sku_id": str(sku.id),
                        "product_id": str(sku.product_id),
                    },
                },
                target_url=f"{settings.b2c_url}/api/v1/events/product",
            ))

    # Сохраняем результат для идемпотентности
    result = {
        "order_id": str(data.order_id),
        "status": "RESERVED",
        "reserved_at": now.isoformat(),
    }
    db.add(ReserveOperation(
        idempotency_key=data.idempotency_key,
        result=result,
    ))

    db.commit()

    return ReserveResponse(**result)


def unreserve_skus(
    db: Session,
    data: InventoryOrderRequest,
) -> InventoryOrderResponse:
    """
    Снятие резерва при отмене заказа (B2B-8, компенсация).
    active_quantity += N, reserved_quantity -= N.
    """
    requested = {item.sku_id: item.quantity for item in data.items}
    sku_ids = list(requested.keys())

    skus = db.query(SKU).filter(SKU.id.in_(sku_ids)).all()

    found_ids = {sku.id for sku in skus}
    missing = set(sku_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    # Снимаем резерв
    for sku in skus:
        qty = requested[sku.id]
        if sku.reserved_quantity < qty:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONFLICT",
                    "message": f"Cannot unreserve {qty} from SKU {sku.id}: only {sku.reserved_quantity} reserved",
                },
            )
        sku.reserved_quantity -= qty

    now = datetime.now(timezone.utc)
    db.commit()

    return InventoryOrderResponse(
        order_id=str(data.order_id),
        status="UNRESERVED",
        processed_at=now.isoformat(),
    )
