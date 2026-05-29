"""
Бизнес-логика для накладных.
US-B2B-06: создание и приёмка накладных.
Ownership check: все SKU должны принадлежать seller из JWT.
Товар должен быть MODERATED для создания накладной.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from src.models.invoice import Invoice, InvoiceItem, InvoiceStatus
from src.models.product import Product, ProductStatus
from src.models.sku import SKU
from src.schemas.invoice import (
    InvoiceAcceptRequest,
    InvoiceCreate,
    InvoiceResponse,
    InvoiceItemResponse,
)


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    """Конвертирует ORM-объект в ответ API по протоколу."""
    return InvoiceResponse(
        id=str(invoice.id),
        seller_id=str(invoice.seller_id),
        status=invoice.status.value,
        items=[
            InvoiceItemResponse(
                id=str(item.id),
                sku_id=str(item.sku_id),
                quantity=item.quantity,
                accepted_quantity=item.accepted_quantity,
            )
            for item in invoice.items
        ],
        created_at=invoice.created_at.isoformat() if invoice.created_at else "",
        updated_at=invoice.updated_at.isoformat() if invoice.updated_at else "",
        accepted_at=invoice.accepted_at.isoformat() if invoice.accepted_at else None,
        accepted_by=str(invoice.accepted_by) if invoice.accepted_by else None,
    )


def _load_invoice(db: Session, invoice_id: uuid.UUID) -> Invoice | None:
    """Загружает накладную со связями."""
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )


def create_invoice(
    db: Session,
    seller_id: uuid.UUID,
    data: InvoiceCreate,
) -> InvoiceResponse:
    """
    Создание накладной (B2B-6).
    Ownership check: каждый SKU должен принадлежать seller из JWT.
    Товар должен быть MODERATED.
    """
    # Собираем все sku_id из запроса
    sku_ids = [item.sku_id for item in data.items]

    # Загружаем SKU с продуктами для проверки
    skus = (
        db.query(SKU)
        .options(joinedload(SKU.product))
        .filter(SKU.id.in_(sku_ids))
        .all()
    )
    found_ids = {sku.id for sku in skus}

    # Проверяем что все SKU найдены
    missing = set(sku_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "SKU not found"},
        )

    # Ownership check: каждый SKU принадлежит seller из JWT
    for sku in skus:
        if sku.product.seller_id != seller_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "NOT_OWNER",
                    "message": "One or more SKUs do not belong to the authenticated seller",
                },
            )

    # Все товары должны быть MODERATED
    for sku in skus:
        if sku.product.status != ProductStatus.MODERATED:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_REQUEST",
                    "message": "Invoice can only be created for MODERATED products",
                },
            )

    # Создаём накладную
    invoice = Invoice(seller_id=seller_id, status=InvoiceStatus.CREATED)
    db.add(invoice)
    db.flush()

    # Добавляем позиции
    item_objs = []
    for item_data in data.items:
        item = InvoiceItem(
            invoice_id=invoice.id,
            sku_id=item_data.sku_id,
            quantity=item_data.quantity,
        )
        db.add(item)
        item_objs.append(item)

    db.commit()

    # Формируем ответ из данных в памяти
    now = datetime.now(timezone.utc).isoformat()
    return InvoiceResponse(
        id=str(invoice.id),
        seller_id=str(seller_id),
        status=InvoiceStatus.CREATED.value,
        items=[
            InvoiceItemResponse(
                id=str(item.id),
                sku_id=str(item.sku_id),
                quantity=item.quantity,
                accepted_quantity=None,
            )
            for item in item_objs
        ],
        created_at=now,
        updated_at=now,
    )


def accept_invoice(
    db: Session,
    invoice_id: uuid.UUID,
    data: InvoiceAcceptRequest | None,
) -> InvoiceResponse:
    """
    Приёмка накладной (B2B-6).
    Если accepted_items не передан → полная приёмка (accepted_quantity = quantity).
    Частичная приёмка: для каждой позиции указывается accepted_quantity.
    Атомарно обновляет stock_quantity SKU.
    """
    invoice = _load_invoice(db, invoice_id)

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Invoice not found"},
        )

    # Нельзя принять уже принятую/отменённую
    if invoice.status != InvoiceStatus.CREATED:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": "Invoice is not in CREATED status"},
        )

    # Полная приёмка или частичная
    if data is None or data.accepted_items is None:
        # Полная приёмка: все позиции принимаются полностью
        for item in invoice.items:
            item.accepted_quantity = item.quantity
    else:
        # Частичная приёмка: маппим invoice_item_id → accepted_quantity
        accept_map = {a.invoice_item_id: a.accepted_quantity for a in data.accepted_items}

        for item in invoice.items:
            if item.id in accept_map:
                accepted = accept_map[item.id]
                # Проверяем что accepted_quantity <= quantity
                if accepted > item.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "INVALID_REQUEST",
                            "message": f"accepted_quantity ({accepted}) > quantity ({item.quantity})",
                        },
                    )
                item.accepted_quantity = accepted
            else:
                # Не указана в запросе → 0 (не принято)
                item.accepted_quantity = 0

    # Обновляем stock_quantity для каждого SKU
    for item in invoice.items:
        if item.accepted_quantity and item.accepted_quantity > 0:
            sku = db.query(SKU).filter(SKU.id == item.sku_id).first()
            if sku:
                sku.stock_quantity += item.accepted_quantity

    # Определяем итоговый статус накладной
    all_full = all(item.accepted_quantity == item.quantity for item in invoice.items)
    all_zero = all((item.accepted_quantity or 0) == 0 for item in invoice.items)

    if all_full:
        invoice.status = InvoiceStatus.ACCEPTED
    elif all_zero:
        invoice.status = InvoiceStatus.CANCELLED
    else:
        invoice.status = InvoiceStatus.PARTIALLY_ACCEPTED

    invoice.accepted_at = datetime.now(timezone.utc)

    db.commit()

    # Перезагружаем для ответа
    invoice = _load_invoice(db, invoice_id)
    return _invoice_to_response(invoice)


def list_invoices(
    db: Session,
    seller_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict:
    """
    Список накладных продавца (B2B-6).
    Только свои — seller_id из JWT.
    """
    from sqlalchemy import func

    query = db.query(Invoice).options(
        joinedload(Invoice.items)
    ).filter(Invoice.seller_id == seller_id)

    if status:
        query = query.filter(Invoice.status == status)

    total = db.query(func.count(Invoice.id)).filter(
        Invoice.seller_id == seller_id
    ).scalar()

    invoices = query.order_by(Invoice.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "items": [_invoice_to_response(inv) for inv in invoices],
        "total_count": total,
        "limit": limit,
        "offset": offset,
    }
