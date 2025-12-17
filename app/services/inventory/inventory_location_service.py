from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.inventory_location_schemas import (
    InventoryLocationCreate,
    InventoryLocationUpdate,
    InventoryLocationOut,
    InventoryLocationListData,
)
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
import logging

logger = logging.getLogger(__name__)

def _map_location(loc: InventoryLocation) -> InventoryLocationOut:
    return InventoryLocationOut(
        id=loc.id,
        code=loc.code,
        name=loc.name,
        is_active=loc.is_active,
        version=loc.version,
        created_at=loc.created_at,
        updated_at=loc.updated_at,
        created_by=loc.created_by_id,
        updated_by=loc.updated_by_id,
        created_by_name=loc.created_by.username if loc.created_by else None,
        updated_by_name=loc.updated_by.username if loc.updated_by else None,
    )

async def create_location(db: AsyncSession, payload: InventoryLocationCreate, user):
    logger.info("Create inventory location", extra={"code": payload.code})

    try:
        location = InventoryLocation(
            code=payload.code.lower(),
            name=payload.name,
            is_active=True,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(location)
        await db.flush()

    except IntegrityError:
        raise AppException(
            409,
            "Location code already exists",
            ErrorCode.LOCATION_CODE_EXISTS,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_LOCATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=location.code,
    )

    await db.commit()
    await db.refresh(location)
    return _map_location(location)

async def list_locations(
    db: AsyncSession,
    active_only: bool,
    page: int,
    page_size: int,
):
    logger.info("List inventory locations", extra={"active_only": active_only})

    query = select(InventoryLocation).where(InventoryLocation.is_deleted.is_(False))

    if active_only:
        query = query.where(InventoryLocation.is_active.is_(True))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    result = await db.execute(
        query.order_by(InventoryLocation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return InventoryLocationListData(
        total=total or 0,
        items=[_map_location(l) for l in result.scalars().all()],
    )

async def update_location(
    db: AsyncSession,
    location_id: int,
    payload: InventoryLocationUpdate,
    user,
):
    current = await db.get(InventoryLocation, location_id)
    if not current or current.is_deleted:
        raise AppException(
            404,
            "Location not found",
            ErrorCode.LOCATION_NOT_FOUND,
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not updates:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    # -------------------------------------------------
    # UNIQUE CODE CHECK (pre-validation)
    # -------------------------------------------------
    if "code" in updates and updates["code"] != current.code:
        exists = await db.scalar(
            select(InventoryLocation.id).where(
                InventoryLocation.code == updates["code"],
                InventoryLocation.id != location_id,
                InventoryLocation.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(
                409,
                "Location code already exists",
                ErrorCode.LOCATION_CODE_EXISTS,
            )

    # -------------------------------------------------
    # CHANGE TRACKING
    # -------------------------------------------------
    changes: list[str] = []
    for k, v in updates.items():
        old = getattr(current, k)
        if old != v:
            changes.append(f"{k}: {old} → {v}")

    if not changes:
        raise AppException(
            400,
            "No actual changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.version == payload.version,
            InventoryLocation.is_deleted.is_(False),
        )
        .values(
            **updates,
            version=InventoryLocation.version + 1,
            updated_by_id=user.id,
        )
        .returning(InventoryLocation)
    )

    try:
        result = await db.execute(stmt)
        location = result.scalar_one_or_none()
    except IntegrityError:
        # race-condition safety net
        raise AppException(
            409,
            "Location code already exists",
            ErrorCode.LOCATION_CODE_EXISTS,
        )

    if not location:
        raise AppException(
            409,
            "Location modified by another process",
            ErrorCode.LOCATION_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_LOCATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=location.code,
        changes=", ".join(changes),
    )

    await db.commit()
    return _map_location(location)

async def deactivate_location(db: AsyncSession, location_id: int, user):
    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.is_active.is_(True),
            InventoryLocation.is_deleted.is_(False),
        )
        .values(
            is_active=False,
            version=InventoryLocation.version + 1,
            updated_by_id=user.id,
        )
        .returning(InventoryLocation)
    )

    result = await db.execute(stmt)
    location = result.scalar_one_or_none()

    if not location:
        raise AppException(
            409,
            "Location already inactive or missing",
            ErrorCode.LOCATION_STATE_INVALID,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DEACTIVATE_LOCATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=location.code,
    )

    await db.commit()
    return _map_location(location)

async def reactivate_location(db: AsyncSession, location_id: int, user):
    stmt = (
        update(InventoryLocation)
        .where(
            InventoryLocation.id == location_id,
            InventoryLocation.is_active.is_(False),
            InventoryLocation.is_deleted.is_(False),
        )
        .values(
            is_active=True,
            version=InventoryLocation.version + 1,
            updated_by_id=user.id,
        )
        .returning(InventoryLocation)
    )

    result = await db.execute(stmt)
    location = result.scalar_one_or_none()

    if not location:
        raise AppException(
            409,
            "Location already active or missing",
            ErrorCode.LOCATION_STATE_INVALID,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.REACTIVATE_LOCATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=location.code,
    )

    await db.commit()
    return _map_location(location)

