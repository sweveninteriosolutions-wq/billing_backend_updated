# app/routers/inventory/warehouse_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.schemas.inventory.warehouse_schemas import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseOut,
    WarehouseListData,
)
from app.services.inventory.warehouse_service import (
    create_warehouse,
    list_warehouses,
    get_warehouse,
    update_warehouse,
    delete_warehouse,
)

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])


@router.post("/", response_model=APIResponse[WarehouseOut])
async def create_warehouse_api(
    payload: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    wh = await create_warehouse(db, payload, user)
    return success_response("Warehouse created successfully", wh)


@router.get("/", response_model=APIResponse[WarehouseListData])
async def list_warehouses_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_inactive: bool = Query(False),
):
    data = await list_warehouses(db, page=page, page_size=page_size, include_inactive=include_inactive)
    return success_response("Warehouses retrieved successfully", data)


@router.get("/{warehouse_id}", response_model=APIResponse[WarehouseOut])
async def get_warehouse_api(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
):
    wh = await get_warehouse(db, warehouse_id)
    return success_response("Warehouse retrieved successfully", wh)


@router.patch("/{warehouse_id}", response_model=APIResponse[WarehouseOut])
async def update_warehouse_api(
    warehouse_id: int,
    payload: WarehouseUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    wh = await update_warehouse(db, warehouse_id, payload, user)
    return success_response("Warehouse updated successfully", wh)


@router.delete("/{warehouse_id}")
async def delete_warehouse_api(
    warehouse_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    result = await delete_warehouse(db, warehouse_id, user)
    return success_response("Warehouse deleted successfully", result)
