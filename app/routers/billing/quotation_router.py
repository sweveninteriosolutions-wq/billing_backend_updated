from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.schemas.billing.quotation_schemas import (
    QuotationCreate,
    QuotationUpdate,
    QuotationOut,
    QuotationListData,
)

from app.services.billing.quotation_service import (
    create_quotation,
    update_quotation,
    approve_quotation,
    delete_quotation,
    get_quotation,
    list_quotations,
    convert_quotation_to_invoice,
)

router = APIRouter(
    prefix="/quotations",
    tags=["Quotations"],
)


@router.post(
    "",
    response_model=APIResponse[QuotationOut],
)
async def create_quotation_api(
    payload: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales"])),
):
    quotation = await create_quotation(db, payload, user)
    return success_response(
        "Quotation created successfully",
        quotation,
    )


@router.get(
    "/ready_for_invoice",
    response_model=APIResponse[QuotationListData],
)
async def list_quotations_ready_for_invoice_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    data = await list_quotations(
        db=db,
        status="converted_to_invoice",
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )
    return success_response(
        "Quotations ready for invoice retrieved successfully",
        data,
    )


@router.get(
    "/{quotation_id}",
    response_model=APIResponse[QuotationOut],
)
async def get_quotation_api(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
):
    quotation = await get_quotation(
        db=db,
        quotation_id=quotation_id,
    )
    return success_response(
        "Quotation retrieved successfully",
        quotation,
    )


@router.get(
    "/",
    response_model=APIResponse[QuotationListData],
)
async def list_quotations_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
    customer_id: int | None = Query(None, description="Filter by customer"),
    status: str | None = Query(None, description="Filter by status (e.g., draft, approved)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    data = await list_quotations(
        db=db,
        customer_id=customer_id,
        status=status,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )
    return success_response(
        "Quotations retrieved successfully",
        data,
    )


@router.patch(
    "/{quotation_id}",
    response_model=APIResponse[QuotationOut],
)
async def update_quotation_api(
    quotation_id: int,
    payload: QuotationUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales"])),
):
    quotation = await update_quotation(
        db=db,
        quotation_id=quotation_id,
        payload=payload,
        user=user,
    )
    return success_response(
        "Quotation updated successfully",
        quotation,
    )


@router.post(
    "/{quotation_id}/approve",
    response_model=APIResponse[QuotationOut],
)
async def approve_quotation_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    quotation = await approve_quotation(
        db=db,
        quotation_id=quotation_id,
        version=version,
        user=user,
    )
    return success_response(
        "Quotation approved successfully",
        quotation,
    )


@router.delete(
    "/{quotation_id}",
    response_model=APIResponse[QuotationOut],
)
async def delete_quotation_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    quotation = await delete_quotation(
        db=db,
        quotation_id=quotation_id,
        version=version,
        user=user,
    )
    return success_response(
        "Quotation deleted successfully",
        quotation,
    )


@router.post(
    "/{quotation_id}/convert-to-invoice",
    response_model=APIResponse[QuotationOut],
)
async def convert_quotation_to_invoice_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
):
    quotation = await convert_quotation_to_invoice(
        db=db,
        quotation_id=quotation_id,
        version=version,
        user=user,
    )
    return success_response(
        "Quotation converted to invoice successfully",
        quotation,
    )
