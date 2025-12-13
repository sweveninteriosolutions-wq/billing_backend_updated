from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.masters.supplier_schemas import (
    SupplierCreateSchema,
    SupplierUpdateSchema,
    SupplierResponseSchema,
    SupplierListResponseSchema,
)
from app.services.masters.supplier_service import (
    create_supplier,
    list_suppliers,
    get_supplier,
    update_supplier,
    deactivate_supplier,
    reactivate_supplier,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.post("/", response_model=SupplierResponseSchema)
async def create_supplier_api(
    payload: SupplierCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    supplier = await create_supplier(db, payload, current_user)
    return {"msg": "Supplier created successfully", "data": supplier}


@router.get("/", response_model=SupplierListResponseSchema)
async def list_suppliers_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    total, suppliers = await list_suppliers(
        db, search, page, page_size, sort_by, order
    )
    return {
        "msg": "Suppliers fetched",
        "total": total,
        "data": suppliers,
    }



@router.get("/{supplier_id}", response_model=SupplierResponseSchema)
async def get_supplier_api(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    return {"msg": "Supplier fetched", "data": await get_supplier(db, supplier_id)}


@router.patch("/{supplier_id}", response_model=SupplierResponseSchema)
async def update_supplier_api(
    supplier_id: int,
    payload: SupplierUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    supplier = await update_supplier(db, supplier_id, payload, current_user)
    return {"msg": "Supplier updated successfully", "data": supplier}


@router.patch(
    "/{supplier_id}/deactivate",
    response_model=SupplierResponseSchema,
)
async def deactivate_supplier_api(
    supplier_id: int,
    payload: SupplierUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    supplier = await deactivate_supplier(
        db=db,
        supplier_id=supplier_id,
        payload=payload,
        current_user=current_user,
    )
    return {
        "msg": "Supplier deactivated successfully",
        "data": supplier,
    }


@router.patch(
    "/{supplier_id}/activate",
    response_model=SupplierResponseSchema,
)
async def reactivate_supplier_api(
    supplier_id: int,
    payload: SupplierUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    supplier = await reactivate_supplier(
        db=db,
        supplier_id=supplier_id,
        payload=payload,
        current_user=current_user,
    )
    return {
        "msg": "Supplier reactivated successfully",
        "data": supplier,
    }
