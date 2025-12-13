# app/routers/inventory/location_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.services.inventory.location_service import (
    create_location,
    list_locations,
    update_location,
    deactivate_location,
    reactivate_location,
)
from app.schemas.inventory.location_schemas import (
    InventoryLocationCreateSchema,
    InventoryLocationUpdateSchema,
    InventoryLocationResponseSchema,
    InventoryLocationListResponseSchema,
)

router = APIRouter(prefix="/inventory/locations", tags=["Inventory Locations"])

@router.post("/", response_model=InventoryLocationResponseSchema)
async def create_location_api(
    payload: InventoryLocationCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    loc = await create_location(db, payload, current_user)
    return {"msg": "Location created", "data": loc}

@router.get("/", response_model=InventoryLocationListResponseSchema)
async def list_locations_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    total, data = await list_locations(db, active_only, page, page_size)
    return {"msg": "Locations fetched", "total": total, "data": data}

@router.patch("/{location_id}", response_model=InventoryLocationResponseSchema)
async def update_location_api(
    location_id: int,
    payload: InventoryLocationUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    loc = await update_location(db, location_id, payload, current_user)
    return {"msg": "Location updated", "data": loc}

@router.delete("/{location_id}", response_model=InventoryLocationResponseSchema)
async def deactivate_location_api(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    loc = await deactivate_location(db, location_id, current_user)
    return {"msg": "Location deactivated", "data": loc}

@router.post("/{location_id}/activate", response_model=InventoryLocationResponseSchema)
async def reactivate_location_api(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    loc = await reactivate_location(db, location_id, current_user)
    return {"msg": "Location reactivated", "data": loc}