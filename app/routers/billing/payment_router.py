from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from decimal import Decimal

from app.core.db import get_db
from app.schemas.billing.payment_schemas import (
    PaymentResponse,
    PaymentListResponse,
)
from app.services.billing.payment_service import (
    get_payment,
    list_payments,
    list_payments_by_customer,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/payments", tags=["Payments"])


# =====================================================
# GET BY ID
# =====================================================
@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment_api(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "billing"])),
):
    return await get_payment(db, payment_id)


# =====================================================
# LIST ALL PAYMENTS (FILTERS)
# =====================================================
@router.get("/", response_model=PaymentListResponse)
async def list_payments_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "billing"])),

    invoice_id: int | None = Query(None),
    customer_id: int | None = Query(None),
    payment_method: str | None = Query(None),

    min_amount: Decimal | None = Query(None, ge=0),
    max_amount: Decimal | None = Query(None, ge=0),

    start_date: date | None = Query(None),
    end_date: date | None = Query(None),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    return await list_payments(
        db=db,
        invoice_id=invoice_id,
        customer_id=customer_id,
        payment_method=payment_method,
        min_amount=min_amount,
        max_amount=max_amount,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )


# =====================================================
# LIST PAYMENTS BY CUSTOMER
# =====================================================
@router.get(
    "/by-customer/{customer_id}",
    response_model=PaymentListResponse,
)
async def list_payments_by_customer_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "billing"])),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await list_payments_by_customer(
        db=db,
        customer_id=customer_id,
        page=page,
        page_size=page_size,
    )
