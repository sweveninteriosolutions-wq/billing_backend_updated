from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from fastapi import HTTPException
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import noload, selectinload

from app.models.billing.payment_models import Payment
from app.models.billing.invoice_models import Invoice
from app.schemas.billing.payment_schemas import (
    PaymentOut,
    PaymentResponse,
    PaymentListResponse,
)


# =====================================================
# MAPPER
# =====================================================
def _map_payment(payment: Payment) -> PaymentOut:
    return PaymentOut.model_validate(payment)


# =====================================================
# GET PAYMENT BY ID
# =====================================================
async def get_payment(
    db: AsyncSession,
    payment_id: int,
) -> PaymentResponse:

    result = await db.execute(
        select(Payment)
        .options(
            noload("*")  # 🔥 disable all relationships
        )
        .where(Payment.id == payment_id)
    )

    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")

    return PaymentResponse(
        message="Payment retrieved successfully",
        data=_map_payment(payment),
    )



# =====================================================
# LIST PAYMENTS (GLOBAL FILTERS)
# =====================================================
async def list_payments(
    db: AsyncSession,
    *,
    invoice_id: int | None,
    customer_id: int | None,
    payment_method: str | None,
    min_amount: Decimal | None,
    max_amount: Decimal | None,
    start_date: date | None,
    end_date: date | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
) -> PaymentListResponse:

    query = (
        select(Payment)
        .options(
            noload("*")  # 🔥 prevent relationship loading
        )
        .join(Invoice, Payment.invoice_id == Invoice.id)
    )

    if invoice_id:
        query = query.where(Payment.invoice_id == invoice_id)

    if customer_id:
        query = query.where(Invoice.customer_id == customer_id)

    if payment_method:
        query = query.where(Payment.payment_method == payment_method)

    if min_amount is not None:
        query = query.where(Payment.amount >= min_amount)

    if max_amount is not None:
        query = query.where(Payment.amount <= max_amount)

    if start_date:
        query = query.where(Payment.created_at >= start_date)

    if end_date:
        query = query.where(Payment.created_at <= end_date)

    sort_map = {
        "created_at": Payment.created_at,
        "amount": Payment.amount,
    }
    sort_col = sort_map.get(sort_by, Payment.created_at)

    query = query.order_by(
        asc(sort_col) if order == "asc" else desc(sort_col)
    )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    )

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )

    payments = result.scalars().all()

    return PaymentListResponse(
        message="Payments retrieved successfully",
        total=total or 0,
        data=[_map_payment(p) for p in payments],
    )



# =====================================================
# LIST PAYMENTS BY CUSTOMER (DEDICATED)
# =====================================================
async def list_payments_by_customer(
    db: AsyncSession,
    customer_id: int,
    *,
    page: int,
    page_size: int,
) -> PaymentListResponse:

    query = (
        select(Payment)
        .options(
            noload("*")  # 🔥 critical
        )
        .join(Invoice, Payment.invoice_id == Invoice.id)
        .where(Invoice.customer_id == customer_id)
        .order_by(Payment.created_at.desc())
    )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    )

    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )

    payments = result.scalars().all()

    return PaymentListResponse(
        message="Customer payments retrieved successfully",
        total=total or 0,
        data=[_map_payment(p) for p in payments],
    )
