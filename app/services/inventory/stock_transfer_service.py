from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.inventory.stock_transfer_models import StockTransfer
from app.models.inventory.inventory_location_models import InventoryLocation
from app.models.inventory.inventory_balance_models import InventoryBalance
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
from app.services.inventory.inventory_movement_service import apply_inventory_movement
from sqlalchemy import func
from app.models.enums.stock_transfer_status import TransferStatus


async def create_stock_transfer(
    db: AsyncSession,
    *,
    product_id: int,
    quantity: int,
    from_location_id: int,
    to_location_id: int,
    current_user,
):
    if quantity <= 0:
        raise HTTPException(400, "Transfer quantity must be positive")

    if from_location_id == to_location_id:
        raise HTTPException(400, "Source and destination locations must differ")

    # Validate locations
    locations = await db.execute(
        select(InventoryLocation)
        .where(
            InventoryLocation.id.in_([from_location_id, to_location_id]),
            InventoryLocation.is_active.is_(True),
        )
    )
    if len(locations.scalars().all()) != 2:
        raise HTTPException(400, "Invalid or inactive location")

    # Validate stock availability (NO LOCK YET)
    balance = await db.scalar(
        select(InventoryBalance.quantity)
        .where(
            InventoryBalance.product_id == product_id,
            InventoryBalance.location_id == from_location_id,
        )
    )
    if balance is None or balance < quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insufficient stock at source location",
        )

    transfer = StockTransfer(
        product_id=product_id,
        quantity=quantity,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        transferred_by_id=current_user.id,
    )

    db.add(transfer)
    await db.flush()

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_STOCK_TRANSFER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=str(transfer.id),
    )

    await db.commit()
    await db.refresh(transfer)
    return transfer

from app.constants.inventory_movement_type import InventoryMovementType

from sqlalchemy.orm import noload

async def complete_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
    current_user,
):
    # ------------------------------------
    # 1. LOCK TRANSFER ROW (NO JOINS)
    # ------------------------------------
    result = await db.execute(
        select(StockTransfer)
        .options(noload("*"))  # 🔥 CRITICAL FIX
        .where(
            StockTransfer.id == transfer_id,
            StockTransfer.is_deleted.is_(False),
        )
        .with_for_update()
    )
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(404, "Stock transfer not found")

    if transfer.status != TransferStatus.pending:
        raise HTTPException(
            400, "Only pending transfers can be completed"
        )

    # ------------------------------------
    # 2. INVENTORY MOVEMENTS (ATOMIC)
    # ------------------------------------
    await apply_inventory_movement(
        db=db,
        product_id=transfer.product_id,
        location_id=transfer.from_location_id,
        quantity_change=-transfer.quantity,
        movement_type=InventoryMovementType.TRANSFER_OUT,
        reference_type="TRANSFER",
        reference_id=transfer.id,
        actor_user=current_user,
    )

    await apply_inventory_movement(
        db=db,
        product_id=transfer.product_id,
        location_id=transfer.to_location_id,
        quantity_change=transfer.quantity,
        movement_type=InventoryMovementType.TRANSFER_IN,
        reference_type="TRANSFER",
        reference_id=transfer.id,
        actor_user=current_user,
    )

    # ------------------------------------
    # 3. UPDATE STATE
    # ------------------------------------
    transfer.status = TransferStatus.completed
    transfer.completed_by_id = current_user.id
    transfer.updated_by_id = current_user.id

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.COMPLETE_STOCK_TRANSFER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=str(transfer.id),
    )

    await db.commit()

    # ------------------------------------
    # 4. OPTIONAL REFRESH (NO LOCK)
    # ------------------------------------
    await db.refresh(transfer)

    return transfer

from sqlalchemy import select
from sqlalchemy.orm import noload

async def cancel_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
    current_user,
):
    # ------------------------------------
    # 1. LOCK TRANSFER ROW (NO JOINS)
    # ------------------------------------
    result = await db.execute(
        select(StockTransfer)
        .options(noload("*"))  # 🔥 CRITICAL
        .where(
            StockTransfer.id == transfer_id,
            StockTransfer.is_deleted.is_(False),
        )
        .with_for_update()
    )
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(404, "Stock transfer not found")

    if transfer.status != TransferStatus.pending:
        raise HTTPException(
            400, "Only pending transfers can be cancelled"
        )

    # ------------------------------------
    # 2. STATE CHANGE
    # ------------------------------------
    transfer.status = TransferStatus.cancelled
    transfer.updated_by_id = current_user.id

    # ------------------------------------
    # 3. ACTIVITY LOG (NO COMMIT HERE)
    # ------------------------------------
    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CANCEL_STOCK_TRANSFER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=str(transfer.id),
    )

    # ------------------------------------
    # 4. COMMIT ATOMICALLY
    # ------------------------------------
    await db.commit()

    # Optional: refresh for clean response
    await db.refresh(transfer)

    return transfer

from sqlalchemy import select
from sqlalchemy.orm import noload

async def get_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
):
    result = await db.execute(
        select(StockTransfer)
        .options(noload("*"))  # 🔥 NO JOINS
        .where(
            StockTransfer.id == transfer_id,
            StockTransfer.is_deleted.is_(False),
        )
    )
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(404, "Stock transfer not found")

    return transfer

from sqlalchemy import select, func, desc
from sqlalchemy.orm import noload

async def list_stock_transfers(
    db: AsyncSession,
    *,
    product_id: int | None,
    status: TransferStatus | None,
    from_location_id: int | None,
    to_location_id: int | None,
    page: int,
    page_size: int,
):
    base = (
        select(StockTransfer)
        .options(noload("*"))  # 🔥 ABSOLUTELY REQUIRED
        .where(StockTransfer.is_deleted.is_(False))
    )

    if product_id:
        base = base.where(StockTransfer.product_id == product_id)

    if status:
        base = base.where(StockTransfer.status == status)

    if from_location_id:
        base = base.where(
            StockTransfer.from_location_id == from_location_id
        )

    if to_location_id:
        base = base.where(
            StockTransfer.to_location_id == to_location_id
        )

    # ---- COUNT (NO ORDER BY) ----
    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    # ---- DATA ----
    result = await db.execute(
        base
        .order_by(StockTransfer.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    transfers = result.scalars().all()

    return total or 0, transfers
