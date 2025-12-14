from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.location_schemas import (
    InventoryLocationCreateSchema,
    InventoryLocationUpdateSchema,
    InventoryLocationTableSchema,
)
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity


# =====================================================
# MAPPER
# =====================================================
def _map_location(loc: InventoryLocation) -> InventoryLocationTableSchema:
    return InventoryLocationTableSchema(
        id=loc.id,
        code=loc.code,
        name=loc.name,
        is_active=loc.is_active,
        version=loc.version,
        created_at=loc.created_at,
        updated_at=loc.updated_at,
        created_by_id=loc.created_by_id,
        updated_by_id=loc.updated_by_id,
        created_by_name=loc.created_by.username if loc.created_by else None,
        updated_by_name=loc.updated_by.username if loc.updated_by else None,
    )


# =====================================================
# CREATE LOCATION
# =====================================================
async def create_location(
    db: AsyncSession,
    payload: InventoryLocationCreateSchema,
    current_user,
):
    location = InventoryLocation(
        code=payload.code.lower(),
        name=payload.name,
        created_by_id=current_user.id,
    )

    db.add(location)

    try:
        await emit_activity(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            code=ActivityCode.CREATE_LOCATION,
            actor_role=current_user.role.capitalize(),
            actor_email=current_user.username,
            target_name=payload.code.lower(),
        )

        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Location code already exists",
        )

    await db.refresh(location)
    return _map_location(location)


# =====================================================
# LIST LOCATIONS
# =====================================================
async def list_locations(
    db: AsyncSession,
    active_only: bool,
    page: int,
    page_size: int,
):
    base = select(InventoryLocation)

    if active_only:
        base = base.where(InventoryLocation.is_active.is_(True))

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(
        base.order_by(InventoryLocation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return total, [_map_location(l) for l in result.scalars().all()]


# =====================================================
# UPDATE LOCATION (OPTIMISTIC LOCK)
# =====================================================
async def update_location(
    db: AsyncSession,
    location_id: int,
    payload: InventoryLocationUpdateSchema,
    current_user,
):
    existing = await db.get(InventoryLocation, location_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes provided",
        )

    changes: list[str] = []

    for field, value in updates.items():
        old = getattr(existing, field)
        if old != value:
            changes.append(f"{field}: {old} → {value}")

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No actual changes detected",
        )

    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.version == payload.version,
        )
        .values(
            **updates,
            version=InventoryLocation.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(InventoryLocation)
    )

    result = await db.execute(stmt)
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Location was modified by another process",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_LOCATION,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=location.code,
        changes=", ".join(changes),
    )

    await db.commit()
    return _map_location(location)


# =====================================================
# DEACTIVATE LOCATION
# =====================================================
async def deactivate_location(
    db: AsyncSession,
    location_id: int,
    current_user,
):
    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.is_active.is_(True),
        )
        .values(
            is_active=False,
            version=InventoryLocation.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(InventoryLocation)
    )

    result = await db.execute(stmt)
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Location not found or already inactive",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DEACTIVATE_LOCATION,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=location.code,
    )

    await db.commit()
    return _map_location(location)


# =====================================================
# REACTIVATE LOCATION
# =====================================================
async def reactivate_location(
    db: AsyncSession,
    location_id: int,
    current_user,
):
    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.is_active.is_(False),
        )
        .values(
            is_active=True,
            version=InventoryLocation.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(InventoryLocation)
    )

    result = await db.execute(stmt)
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Location not found or already active",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.REACTIVATE_LOCATION,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=location.code,
    )

    await db.commit()
    return _map_location(location)
