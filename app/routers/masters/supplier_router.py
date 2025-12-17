from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.masters.supplier_schemas import (
    SupplierCreate,
    SupplierUpdate,
    SupplierOut,
    SupplierListData,
    VersionPayload,
)
from app.services.masters.supplier_service import (
    create_supplier,
    get_supplier,
    list_suppliers,
    update_supplier,
    deactivate_supplier,
)
from app.utils.check_roles import require_role
from app.utils.response import APIResponse, success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])
logger = get_logger(__name__)


@router.post("/", response_model=APIResponse[SupplierOut])
async def create_supplier_api(
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    logger.info(
        "Create supplier",
        extra={"supplier_name": payload.name, "email": payload.email},
    )

    supplier = await create_supplier(db, payload, user)
    return success_response("Supplier created successfully", supplier)


@router.get("/{supplier_id}", response_model=APIResponse[SupplierOut])
async def get_supplier_api(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    logger.info("Get supplier", extra={"supplier_id": supplier_id})

    supplier = await get_supplier(db, supplier_id)
    return success_response("Supplier fetched successfully", supplier)


@router.get("/", response_model=APIResponse[SupplierListData])
async def list_suppliers_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),

    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),

    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    logger.info(
        "List suppliers",
        extra={
            "search": search,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )

    data = await list_suppliers(
        db=db,
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return success_response("Suppliers fetched successfully", data)


@router.patch("/{supplier_id}", response_model=APIResponse[SupplierOut])
async def update_supplier_api(
    supplier_id: int,
    payload: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    logger.info("Update supplier", extra={"supplier_id": supplier_id})

    supplier = await update_supplier(db, supplier_id, payload, user)
    return success_response("Supplier updated successfully", supplier)


@router.patch(
    "/{supplier_id}/deactivate",
    response_model=APIResponse[SupplierOut],
)
async def deactivate_supplier_api(
    supplier_id: int,
    payload: VersionPayload,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info(
        "Deactivate supplier",
        extra={
            "supplier_id": supplier_id,
            "version": payload.version,
            "actor_id": user.id,
        },
    )

    supplier = await deactivate_supplier(
        db=db,
        supplier_id=supplier_id,
        version=payload.version,
        user=user,
    )

    return success_response("Supplier deactivated successfully", supplier)