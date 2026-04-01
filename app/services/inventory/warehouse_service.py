# app/services/inventory/warehouse_service.py
# ERP-023 FIXED: All list/get queries now filter by is_deleted.is_(False).
#                delete_warehouse sets both is_active=False and is_deleted=True;
#                previously the list query only checked is_active, so deleted
#                warehouses appeared when include_inactive=True was passed.

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.inventory.warehouse_models import Warehouse
from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.warehouse_schemas import (
    WarehouseCreate,
    WarehouseUpdate,
    WarehouseOut,
    WarehouseListItem,
    WarehouseListData,
)
from app.constants.error_codes import ErrorCode
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def _map_warehouse(wh: Warehouse) -> WarehouseOut:
    return WarehouseOut(
        id=wh.id,
        code=wh.code,
        name=wh.name,
        address=wh.address,
        city=wh.city,
        state=wh.state,
        pincode=wh.pincode,
        gstin=wh.gstin,
        phone=wh.phone,
        is_active=wh.is_active,
        version=wh.version,
        created_at=wh.created_at,
        updated_at=wh.updated_at,
    )


async def create_warehouse(
    db: AsyncSession, payload: WarehouseCreate, user
) -> WarehouseOut:
    existing = await db.scalar(
        select(Warehouse.id).where(
            Warehouse.code == payload.code.upper(),
            Warehouse.is_deleted.is_(False),
        )
    )
    if existing:
        raise AppException(409, f"Warehouse code '{payload.code}' already exists", ErrorCode.DUPLICATE_ENTRY)

    existing_name = await db.scalar(
        select(Warehouse.id).where(
            Warehouse.name == payload.name,
            Warehouse.is_deleted.is_(False),
        )
    )
    if existing_name:
        raise AppException(409, f"Warehouse name '{payload.name}' already exists", ErrorCode.DUPLICATE_ENTRY)

    wh = Warehouse(
        code=payload.code.upper(),
        name=payload.name,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        pincode=payload.pincode,
        gstin=payload.gstin,
        phone=payload.phone,
        is_active=payload.is_active,
        version=1,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    logger.info(f"Warehouse created: {wh.code} by user {user.id}")
    return _map_warehouse(wh)


async def list_warehouses(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    include_inactive: bool = False,
) -> WarehouseListData:
    # ERP-023 FIXED: Always filter out soft-deleted warehouses regardless of include_inactive.
    filters = [Warehouse.is_deleted.is_(False)]
    if not include_inactive:
        filters.append(Warehouse.is_active.is_(True))

    total = await db.scalar(
        select(func.count(Warehouse.id)).where(*filters)
    )

    rows = (
        await db.execute(
            select(Warehouse)
            .where(*filters)
            .order_by(Warehouse.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # Get location counts per warehouse in one query
    loc_counts_result = await db.execute(
        select(
            InventoryLocation.warehouse_id,
            func.count(InventoryLocation.id).label("cnt"),
        )
        .where(InventoryLocation.is_deleted.is_(False))
        .group_by(InventoryLocation.warehouse_id)
    )
    loc_counts = {r.warehouse_id: r.cnt for r in loc_counts_result.all()}

    items = [
        WarehouseListItem(
            id=wh.id,
            code=wh.code,
            name=wh.name,
            city=wh.city,
            state=wh.state,
            is_active=wh.is_active,
            locations_count=loc_counts.get(wh.id, 0),
        )
        for wh in rows
    ]
    return WarehouseListData(total=total or 0, items=items)


async def get_warehouse(db: AsyncSession, warehouse_id: int) -> WarehouseOut:
    # ERP-023 FIXED: Filter by is_deleted.
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.is_deleted.is_(False),
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise AppException(404, "Warehouse not found", ErrorCode.NOT_FOUND)
    return _map_warehouse(wh)


async def update_warehouse(
    db: AsyncSession, warehouse_id: int, payload: WarehouseUpdate, user
) -> WarehouseOut:
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.is_deleted.is_(False),
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise AppException(404, "Warehouse not found", ErrorCode.NOT_FOUND)

    if wh.version != payload.version:
        raise AppException(409, "Warehouse modified by another process. Refresh and retry.", ErrorCode.VERSION_CONFLICT)

    if payload.name is not None and payload.name != wh.name:
        dup = await db.scalar(
            select(Warehouse.id).where(
                Warehouse.name == payload.name,
                Warehouse.id != warehouse_id,
                Warehouse.is_deleted.is_(False),
            )
        )
        if dup:
            raise AppException(409, f"Warehouse name '{payload.name}' already exists", ErrorCode.DUPLICATE_ENTRY)
        wh.name = payload.name

    if payload.address is not None:
        wh.address = payload.address
    if payload.city is not None:
        wh.city = payload.city
    if payload.state is not None:
        wh.state = payload.state
    if payload.pincode is not None:
        wh.pincode = payload.pincode
    if payload.gstin is not None:
        wh.gstin = payload.gstin
    if payload.phone is not None:
        wh.phone = payload.phone
    if payload.is_active is not None:
        wh.is_active = payload.is_active

    wh.version += 1
    wh.updated_by_id = user.id

    await db.commit()
    await db.refresh(wh)
    return _map_warehouse(wh)


async def delete_warehouse(db: AsyncSession, warehouse_id: int, user) -> dict:
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.is_deleted.is_(False),
        )
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise AppException(404, "Warehouse not found", ErrorCode.NOT_FOUND)

    active_locs = await db.scalar(
        select(func.count(InventoryLocation.id)).where(
            InventoryLocation.warehouse_id == warehouse_id,
            InventoryLocation.is_deleted.is_(False),
            InventoryLocation.is_active.is_(True),
        )
    )
    if active_locs and active_locs > 0:
        raise AppException(
            400,
            f"Cannot delete warehouse with {active_locs} active location(s). Deactivate them first.",
            ErrorCode.VALIDATION_ERROR,
        )

    # ERP-023 FIXED: Soft-delete. Both flags set; list/get queries filter by is_deleted.
    wh.is_active = False
    wh.is_deleted = True
    wh.updated_by_id = user.id
    await db.commit()
    return {"id": warehouse_id, "deleted": True}
