from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse
from app.services.inventory.inventory_location_service import (
    create_location,
    list_locations,
    update_location,
    deactivate_location,
    reactivate_location,
)
from app.schemas.inventory.inventory_location_schemas import (
    InventoryLocationCreate,
    InventoryLocationUpdate,
    InventoryLocationOut,
    InventoryLocationListData,
)

router = APIRouter(
    prefix="/inventory/locations",
    tags=["Inventory Locations"],
)


# =========================
# CREATE
# =========================
@router.post("/", response_model=APIResponse[InventoryLocationOut])
async def create_location_api(
    payload: InventoryLocationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    location = await create_location(db, payload, user)
    return success_response("Location created successfully", location)


# =========================
# LIST
# =========================
@router.get("/", response_model=APIResponse[InventoryLocationListData])
async def list_locations_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data = await list_locations(
        db=db,
        active_only=active_only,
        page=page,
        page_size=page_size,
    )
    return success_response("Locations fetched successfully", data)


# =========================
# UPDATE
# =========================
@router.patch("/{location_id}", response_model=APIResponse[InventoryLocationOut])
async def update_location_api(
    location_id: int,
    payload: InventoryLocationUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    location = await update_location(db, location_id, payload, user)
    return success_response("Location updated successfully", location)


# =========================
# DEACTIVATE
# =========================
@router.patch(
    "/{location_id}/deactivate",
    response_model=APIResponse[InventoryLocationOut],
)
async def deactivate_location_api(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    location = await deactivate_location(db, location_id, user)
    return success_response("Location deactivated successfully", location)


# =========================
# REACTIVATE
# =========================
@router.patch(
    "/{location_id}/activate",
    response_model=APIResponse[InventoryLocationOut],
)
async def reactivate_location_api(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    location = await reactivate_location(db, location_id, user)
    return success_response("Location reactivated successfully", location)
