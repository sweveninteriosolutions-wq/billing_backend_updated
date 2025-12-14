# app/routers/inventory/grn_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role

from app.schemas.inventory.grn_schemas import (
    GRNCreateSchema,
    GRNResponseSchema,
    GRNListResponseSchema,
    GRNUpdateSchema,
)

from app.services.inventory.grn_service import (
    create_grn,
    verify_grn,
    delete_grn,
    list_grns,
    get_grn,
    update_grn,
)

router = APIRouter(prefix="/grns", tags=["GRN"])

@router.post("/", response_model=GRNResponseSchema)
async def create_grn_api(
    payload: GRNCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    grn = await create_grn(db, payload, current_user)
    return {
        "msg": "GRN created successfully",
        "data": grn,
    }

@router.get("/", response_model=GRNListResponseSchema)
async def list_grns_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),

    supplier_id: int | None = Query(None),
    status: str | None = Query(None),

    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    total, grns = await list_grns(
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

    return {
        "msg": "GRNs fetched successfully",
        "total": total,
        "data": grns,
    }

@router.get("/{grn_id}", response_model=GRNResponseSchema)
async def get_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    grn = await get_grn(db, grn_id)
    return {
        "msg": "GRN fetched successfully",
        "data": grn,
    }

@router.patch("/{grn_id}", response_model=GRNResponseSchema)
async def update_grn_api(
    grn_id: int,
    payload: GRNUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    grn_data = await update_grn(db, grn_id, payload, current_user)
    return {
        "msg": "GRN updated successfully",
        "data": grn_data,
    }


@router.post("/{grn_id}/verify", response_model=GRNResponseSchema)
async def verify_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    grn = await verify_grn(db, grn_id, current_user)
    return {
        "msg": "GRN verified successfully",
        "data": grn,
    }

@router.delete("/{grn_id}", response_model=GRNResponseSchema)
async def delete_grn_api(
    grn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    grn = await delete_grn(db, grn_id, current_user)
    return {
        "msg": "GRN deleted successfully",
        "data": grn,
    }

