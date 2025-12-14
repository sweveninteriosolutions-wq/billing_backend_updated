from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Query

from app.core.db import get_db
from app.schemas.billing.invoice_schemas import *
from app.services.billing.invoice_service import *
from app.utils.check_roles import require_role

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.post("", response_model=InvoiceResponse)
async def create_invoice_api(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"]))
):
    return await create_invoice(db, payload, user)


@router.post("/{invoice_id}/verify", response_model=InvoiceResponse)
async def verify_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await verify_invoice(db, invoice_id, user)


@router.post("/{invoice_id}/discount", response_model=InvoiceResponse)
async def apply_discount_api(
    invoice_id: int,
    payload: InvoiceDiscountApply,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await apply_discount(db, invoice_id, payload, user)


@router.post("/{invoice_id}/payments", response_model=PaymentResponse)
async def add_payment_api(
    invoice_id: int,
    payload: InvoicePaymentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"]))
):
    return await add_payment(db, invoice_id, payload, user)


@router.post("/{invoice_id}/fulfill", response_model=InvoiceResponse)
async def fulfill_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await fulfill_invoice(db, invoice_id, user)

@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"]))
):
    return await get_invoice(db, invoice_id)


@router.get("")
async def list_invoices_route(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    include_total: bool = Query(False),  # 👈 frontend decides
    db: AsyncSession = Depends(get_db),
):
    return await list_invoices(
        db,
        page=page,
        page_size=page_size,
        include_total=include_total,
    )



@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice_api(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await update_invoice(db, invoice_id, payload, user)


@router.post("/{invoice_id}/override-discount", response_model=InvoiceResponse)
async def override_discount_api(
    invoice_id: int,
    payload: InvoiceAdminDiscountOverride,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await override_invoice_discount(db, invoice_id, payload, user)


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return await cancel_invoice(db, invoice_id, user)
