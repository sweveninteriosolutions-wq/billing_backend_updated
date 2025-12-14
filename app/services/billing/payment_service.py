from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

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
        .options(noload("*"))
        .where(Payment.id == payment_id)
    )

    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

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
    invoice_id: int | None = None,
    customer_id: int | None = None,
    payment_method: str | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    order: str = "desc",
) -> PaymentListResponse:

    # -------------------------------
    # BASE QUERY (NO ORDER BY)
    # -------------------------------
    base_query = (
        select(Payment)
        .options(noload("*"))
        .join(Invoice, Payment.invoice_id == Invoice.id)
    )

    if invoice_id:
        base_query = base_query.where(Payment.invoice_id == invoice_id)

    if customer_id:
        base_query = base_query.where(Invoice.customer_id == customer_id)

    if payment_method:
        base_query = base_query.where(Payment.payment_method == payment_method)

    if min_amount is not None:
        base_query = base_query.where(Payment.amount >= min_amount)

    if max_amount is not None:
        base_query = base_query.where(Payment.amount <= max_amount)

    if start_date:
        base_query = base_query.where(Payment.created_at >= start_date)

    if end_date:
        base_query = base_query.where(Payment.created_at <= end_date)

    # -------------------------------
    # TOTAL COUNT (NO SORT)
    # -------------------------------
    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )

    # -------------------------------
    # SORT + PAGINATION
    # -------------------------------
    sort_map = {
        "created_at": Payment.created_at,
        "amount": Payment.amount,
    }
    sort_col = sort_map.get(sort_by, Payment.created_at)

    paged_query = (
        base_query
        .order_by(
            asc(sort_col) if order == "asc" else desc(sort_col)
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(paged_query)
    payments = result.scalars().all()

    return PaymentListResponse(
        message="Payments retrieved successfully",
        total=total or 0,
        data=[_map_payment(p) for p in payments],
    )