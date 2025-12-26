from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.schemas.inventory.grn_schemas import (
    GRNCreateSchema,
    GRNUpdateSchema,
    GRNOutSchema,
    GRNListViewData,

)

from app.services.inventory.grn_service import (
    create_grn,
    get_grn,
    update_grn,
    verify_grn,
    delete_grn,
    list_grns_view
)

router = APIRouter(
    prefix="/grns",
    tags=["GRN"],
)

# =========================
# CREATE
# =========================
@router.post("/", response_model=APIResponse[GRNOutSchema])
async def create_grn_api(
    payload: GRNCreateSchema,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    grn = await create_grn(db, payload, user)
    return success_response("GRN created successfully", grn)


# =========================
# LIST
# =========================
@router.get("/", response_model=APIResponse[GRNListViewData])
async def list_grns_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),

    supplier_id: int | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    data = await list_grns_view(
        db=db,
        supplier_id=supplier_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )

    return success_response("GRNs fetched successfully", data)





# =========================
# GET BY ID
# =========================
@router.get("/{grn_id}", response_model=APIResponse[GRNOutSchema])
async def get_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    grn = await get_grn(db, grn_id)
    return success_response("GRN fetched successfully", grn)


# =========================
# UPDATE (DRAFT ONLY)
# =========================
@router.patch("/{grn_id}", response_model=APIResponse[GRNOutSchema])
async def update_grn_api(
    grn_id: int,
    payload: GRNUpdateSchema,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    grn = await update_grn(db, grn_id, payload, user)
    return success_response("GRN updated successfully", grn)


# =========================
# VERIFY (STOCK IN)
# =========================
@router.post("/{grn_id}/verify", response_model=APIResponse[GRNOutSchema])
async def verify_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    grn = await verify_grn(db, grn_id, user)
    return success_response("GRN verified and stock updated", grn)


# =========================
# DELETE (SOFT DELETE, DRAFT ONLY)
# =========================
@router.delete("/{grn_id}", response_model=APIResponse[GRNOutSchema])
async def delete_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    grn = await delete_grn(db, grn_id, user)
    return success_response("GRN deleted successfully", grn)
