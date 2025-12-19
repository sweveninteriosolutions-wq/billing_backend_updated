from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from decimal import Decimal

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.services.billing.payment_service import (
    get_payment,
    list_payments,
)

from app.schemas.billing.payment_schemas import (
    PaymentOut,
    PaymentListData,
)

router = APIRouter(
    prefix="/payments",
    tags=["Payments"],
)


# =====================================================
# GET PAYMENT BY ID
# =====================================================
@router.get(
    "/{payment_id}",
    response_model=APIResponse[PaymentOut],
)
async def get_payment_api(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(["admin", "billing"])),
):
    payment = await get_payment(db, payment_id)
    return success_response("Payment retrieved successfully", payment)


# =====================================================
# LIST PAYMENTS
# =====================================================
@router.get(
    "/",
    response_model=APIResponse[PaymentListData],
)
async def list_payments_api(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(["admin", "billing"])),

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
    data = await list_payments(
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

    return success_response("Payments retrieved successfully", data)
