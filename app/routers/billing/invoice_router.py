from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.schemas.billing.invoice_schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceOut,
    InvoiceListData,
    InvoiceDiscountApply,
    InvoicePaymentCreate,
    InvoiceAdminDiscountOverride,
    PaymentOut,
)

from app.services.billing.invoice_service import (
    create_invoice,
    verify_invoice,
    apply_discount,
    add_payment,
    fulfill_invoice,
    get_invoice,
    list_invoices,
    update_invoice,
    override_invoice_discount,
    cancel_invoice,
)

router = APIRouter(
    prefix="/invoices",
    tags=["Invoices"],
)


@router.post(
    "",
    response_model=APIResponse[InvoiceOut],
)
async def create_invoice_api(
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"])),
):
    invoice = await create_invoice(db, payload, user)
    return success_response(
        "Invoice created successfully",
        invoice,
    )


@router.get(
    "/{invoice_id}",
    response_model=APIResponse[InvoiceOut],
)
async def get_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"])),
):
    invoice = await get_invoice(db, invoice_id)
    return success_response(
        "Invoice retrieved successfully",
        invoice,
    )


@router.get(
    "/",
    response_model=APIResponse[InvoiceListData],
)
async def list_invoices_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"])),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    include_total: bool = Query(False),
):
    data = await list_invoices(
        db=db,
        page=page,
        page_size=page_size,
    )
    return success_response(
        "Invoices retrieved successfully",
        data,
    )


@router.patch(
    "/{invoice_id}",
    response_model=APIResponse[InvoiceOut],
)
async def update_invoice_api(
    invoice_id: int,
    payload: InvoiceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await update_invoice(db, invoice_id, payload, user)
    return success_response(
        "Invoice updated successfully",
        invoice,
    )


@router.post(
    "/{invoice_id}/verify",
    response_model=APIResponse[InvoiceOut],
)
async def verify_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await verify_invoice(db, invoice_id, user)
    return success_response(
        "Invoice verified successfully",
        invoice,
    )


@router.post(
    "/{invoice_id}/discount",
    response_model=APIResponse[InvoiceOut],
)
async def apply_discount_api(
    invoice_id: int,
    payload: InvoiceDiscountApply,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await apply_discount(db, invoice_id, payload, user)
    return success_response(
        "Discount applied successfully",
        invoice,
    )


@router.post(
    "/{invoice_id}/payments",
    response_model=APIResponse[PaymentOut],
)
async def add_payment_api(
    invoice_id: int,
    payload: InvoicePaymentCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"])),
):
    payment = await add_payment(db, invoice_id, payload, user)
    return success_response(
        "Payment added successfully",
        payment,
    )


@router.post(
    "/{invoice_id}/fulfill",
    response_model=APIResponse[InvoiceOut],
)
async def fulfill_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await fulfill_invoice(db, invoice_id, user)
    return success_response(
        "Invoice fulfilled successfully",
        invoice,
    )


@router.post(
    "/{invoice_id}/override-discount",
    response_model=APIResponse[InvoiceOut],
)
async def override_discount_api(
    invoice_id: int,
    payload: InvoiceAdminDiscountOverride,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await override_invoice_discount(db, invoice_id, payload, user)
    return success_response(
        "Discount overridden successfully",
        invoice,
    )


@router.post(
    "/{invoice_id}/cancel",
    response_model=APIResponse[InvoiceOut],
)
async def cancel_invoice_api(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    invoice = await cancel_invoice(db, invoice_id, user)
    return success_response(
        "Invoice cancelled successfully",
        invoice,
    )
