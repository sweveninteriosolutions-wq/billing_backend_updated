# app/routers/billing/quotation_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.billing.quotation_schemas import (
    QuotationCreate,
    QuotationUpdate,
    QuotationResponse,
    QuotationListResponse,
)
from app.services.billing.quotation_service import (
    create_quotation,
    update_quotation,
    approve_quotation,
    delete_quotation,
    get_quotation,
    list_quotations,
    convert_quotation_to_invoice
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/quotations", tags=["Quotations"])


@router.post("/", response_model=QuotationResponse)
async def create_quotation_api(
    payload: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales"])),
):
    return await create_quotation(db, payload, current_user)



# =====================================================
# GET SINGLE QUOTATION
# =====================================================

@router.get(
    "/{quotation_id}",
    response_model=QuotationResponse,
)
async def get_quotation_api(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(
        require_role(["admin", "sales", "cashier"])
    ),
):
    """
    Fetch single quotation with items.
    - Async safe
    - Soft-deleted records excluded
    """
    return await get_quotation(
        db=db,
        quotation_id=quotation_id,
    )


# =====================================================
# LIST QUOTATIONS
# =====================================================

@router.get(
    "/",
    response_model=QuotationListResponse,
)
async def list_quotations_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(
        require_role(["admin", "sales", "cashier"])
    ),

    # -------- Filters --------
    customer_id: int | None = Query(
        None, description="Filter by customer"
    ),
    status: str | None = Query(
        None, description="draft | approved | expired | cancelled"
    ),

    # -------- Pagination --------
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    # -------- Sorting --------
    sort_by: str = Query(
        "created_at",
        description="created_at | quotation_number",
    ),
    order: str = Query(
        "desc",
        description="asc | desc",
    ),
):
    """
    List quotations with pagination and filters.
    """
    return await list_quotations(
        db=db,
        customer_id=customer_id,
        status=status,
        limit=page_size,
        offset=(page - 1) * page_size,
        sort_by=sort_by,
        order=order,
    )


@router.patch("/{quotation_id}", response_model=QuotationResponse)
async def update_quotation_api(
    quotation_id: int,
    payload: QuotationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales"])),
):
    return await update_quotation(db, quotation_id, payload, current_user)


@router.post("/{quotation_id}/approve", response_model=QuotationResponse)
async def approve_quotation_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await approve_quotation(db, quotation_id, version, current_user)


@router.delete("/{quotation_id}", response_model=QuotationResponse)
async def delete_quotation_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await delete_quotation(db, quotation_id, version, current_user)

@router.post("/{quotation_id}/convert-to-invoice", response_model=QuotationResponse)
async def convert_quotation_to_invoice_api(
    quotation_id: int,
    version: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales", "cashier"])),
):
    return await convert_quotation_to_invoice(
        db,
        quotation_id,
        version,
        current_user,
    )

@router.get("/ready_for_invoice", response_model=QuotationListResponse)
async def list_quotations_ready_for_invoice_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(
        require_role(["admin", "sales", "cashier"])
    ),

    # -------- Pagination --------
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    # -------- Sorting --------
    sort_by: str = Query(
        "created_at",
        description="created_at | quotation_number",
    ),
    order: str = Query(
        "desc",
        description="asc | desc",
    ),
):
    """
    List quotations ready to be converted to invoice with pagination.
    """
    return await list_quotations(
        db=db,
        status="converted_to_invoice",
        limit=page_size,
        offset=(page - 1) * page_size,
        sort_by=sort_by,
        order=order,
    )