"""
Бизнес-логика резервирования SKU.
US-B2B-08: reserve (all-or-nothing) и unreserve (компенсация).
SELECT FOR UPDATE для конкурентности на Postgres.
Идемпотентность: reserve по idempotency_key, unreserve по order_id.
Unreserve восстанавливает ровно то, что было зарезервировано под order_id.
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


def _is_postgres(db: Session) -> bool:
    """Проверяем диалект БД — FOR UPDATE работает только на Postgres."""
    return "postgresql" in str(db.bind.url) if db.bind else False


def reserve_skus(
    db: Session,
    data: ReserveRequest,
) -> ReserveResponse:
    """
    All-or-nothing резервирование (B2B-8).
    SELECT FOR UPDATE на Postgres для защиты от гонок.
    Идемпотентность по idempotency_key.
    Сохраняет связь order_id → items в ReserveOperation для unreserve.
    """
    # Идемпотентность — если ключ уже обработан, возвращаем кэш
    existing = db.query(ReserveOperation).filter(
        ReserveOperation.idempotency_key == data.idempotency_key
    ).first()
    if existing:
        return ReserveResponse(**existing.result)

    # Собираем sku_id → quantity
    requested = {item.sku_id: item.quantity for item in data.items}
    sku_ids = list(requested.keys())

    # SELECT FOR UPDATE на Postgres, обычный SELECT на SQLite (тесты)
    query = db.query(SKU).filter(SKU.id.in_(sku_ids))
    if _is_postgres(db):
        query = query.with_for_update()
    skus = query.all()

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

    # Сохраняем результат + связь order_id → items для unreserve
    result = {
        "order_id": str(data.order_id),
        "status": "RESERVED",
        "reserved_at": now.isoformat(),
        # Храним items для проверки при unreserve
        "_reserved_items": [
            {"sku_id": str(item.sku_id), "quantity": item.quantity}
            for item in data.items
        ],
    }
    db.add(ReserveOperation(
        idempotency_key=data.idempotency_key,
        result=result,
    ))

    db.commit()

    return ReserveResponse(
        order_id=str(data.order_id),
        status="RESERVED",
        reserved_at=now.isoformat(),
    )


def unreserve_skus(
    db: Session,
    data: InventoryOrderRequest,
) -> InventoryOrderResponse:
    """
    Снятие резерва при отмене заказа (B2B-8, компенсация).
    Идемпотентность по order_id.
    Восстанавливает ровно то, что было зарезервировано под этот order_id.
    Не доверяет входному quantity — берёт из сохранённой операции.
    """
    now = datetime.now(timezone.utc)

    # Ищем сохранённую операцию резервирования по order_id
    reservation = db.query(ReserveOperation).filter(
        ReserveOperation.result["order_id"].as_string() == str(data.order_id)
    ).first()

    # Fallback: поиск по всем записям (SQLite не поддерживает JSON path)
    if not reservation:
        all_ops = db.query(ReserveOperation).all()
        for op in all_ops:
            if op.result.get("order_id") == str(data.order_id):
                reservation = op
                break

    if not reservation:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Reservation for this order_id not found"},
        )

    # Идемпотентность — если уже снят резерв (статус UNRESERVED), возвращаем кэш
    if reservation.result.get("status") == "UNRESERVED":
        return InventoryOrderResponse(
            order_id=str(data.order_id),
            status="UNRESERVED",
            processed_at=reservation.result.get("unreserved_at", now.isoformat()),
        )

    # Берём items из сохранённой операции (не из запроса — защита от подмены)
    reserved_items = reservation.result.get("_reserved_items", [])
    if not reserved_items:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "No reserved items found for this order"},
        )

    # SELECT FOR UPDATE для Postgres
    sku_ids = [uuid.UUID(item["sku_id"]) for item in reserved_items]
    query = db.query(SKU).filter(SKU.id.in_(sku_ids))
    if _is_postgres(db):
        query = query.with_for_update()
    skus = {sku.id: sku for sku in query.all()}

    # Снимаем резерв по сохранённым данным
    for item in reserved_items:
        sku_id = uuid.UUID(item["sku_id"])
        qty = item["quantity"]
        sku = skus.get(sku_id)
        if sku and sku.reserved_quantity >= qty:
            sku.reserved_quantity -= qty

    # Обновляем статус операции → UNRESERVED (для идемпотентности)
    updated_result = {**reservation.result, "status": "UNRESERVED", "unreserved_at": now.isoformat()}
    reservation.result = updated_result

    db.commit()

    return InventoryOrderResponse(
        order_id=str(data.order_id),
        status="UNRESERVED",
        processed_at=now.isoformat(),
    )


def fulfill_order(
    db: Session,
    data: InventoryOrderRequest,
) -> InventoryOrderResponse:
    """
    Списание резерва при доставке (B2B-10).
    reserved_quantity -= N, stock_quantity -= N (товар покинул склад).
    active_quantity не меняется (stock и reserved уменьшаются одинаково).
    Идемпотентность по order_id через FulfillOperation.
    SELECT FOR UPDATE на Postgres.
    """
    from src.models.outbox import FulfillOperation

    now = datetime.now(timezone.utc)

    # Идемпотентность — если order_id уже обработан, возвращаем кэш
    existing = db.query(FulfillOperation).filter(
        FulfillOperation.order_id == data.order_id
    ).first()
    if existing:
        return InventoryOrderResponse(**existing.result)

    requested = {item.sku_id: item.quantity for item in data.items}
    sku_ids = list(requested.keys())

    # SELECT FOR UPDATE для Postgres
    query = db.query(SKU).filter(SKU.id.in_(sku_ids))
    if _is_postgres(db):
        query = query.with_for_update()
    skus = query.all()

    # Проверяем что все SKU найдены
    found_ids = {sku.id for sku in skus}
    missing = set(sku_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    # Списываем: reserved -= N, stock -= N
    for sku in skus:
        qty = requested[sku.id]
        if sku.reserved_quantity < qty:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONFLICT",
                    "message": f"Cannot fulfill {qty} from SKU {sku.id}: only {sku.reserved_quantity} reserved",
                },
            )
        sku.reserved_quantity -= qty
        sku.stock_quantity -= qty

    # Сохраняем результат для идемпотентности
    result = {
        "order_id": str(data.order_id),
        "status": "FULFILLED",
        "processed_at": now.isoformat(),
    }
    db.add(FulfillOperation(
        order_id=data.order_id,
        result=result,
    ))

    db.commit()

    return InventoryOrderResponse(**result)
