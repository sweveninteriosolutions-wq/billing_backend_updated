# app/services/inventory/inventory_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.inventory_movement_models import InventoryMovement
from app.models.enums.inventory_movement_status import InventoryMovementType
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity


ALLOWED_REFERENCE_TYPES = {
    "GRN",
    "INVOICE",
    "TRANSFER",
    "ADJUSTMENT",
}

POSITIVE_MOVEMENTS = {
    InventoryMovementType.STOCK_IN,
    InventoryMovementType.TRANSFER_IN,
}

NEGATIVE_MOVEMENTS = {
    InventoryMovementType.STOCK_OUT,
    InventoryMovementType.TRANSFER_OUT,
}


async def apply_inventory_movement(
    db: AsyncSession,
    *,
    product_id: int,
    location_id: int,
    quantity_change: int,
    movement_type: InventoryMovementType,
    reference_type: str,
    reference_id: int,
    actor_user,
):
    # ------------------------------------
    # Basic validations
    # ------------------------------------
    if quantity_change == 0:
        raise HTTPException(
            status_code=400,
            detail="Inventory movement quantity cannot be zero",
        )

    if reference_type not in ALLOWED_REFERENCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid inventory reference type",
        )

    if movement_type in POSITIVE_MOVEMENTS and quantity_change < 0:
        raise HTTPException(
            status_code=400,
            detail=f"{movement_type} must have positive quantity",
        )

    if movement_type in NEGATIVE_MOVEMENTS and quantity_change > 0:
        raise HTTPException(
            status_code=400,
            detail=f"{movement_type} must have negative quantity",
        )

    try:
        # ------------------------------------
        # 1. Lock inventory balance row
        # ------------------------------------
        result = await db.execute(
            select(InventoryBalance)
            .where(
                InventoryBalance.product_id == product_id,
                InventoryBalance.location_id == location_id,
            )
            .with_for_update()
        )
        balance = result.scalar_one_or_none()

        # ------------------------------------
        # 2. Create balance row if missing
        # ------------------------------------
        if not balance:
            balance = InventoryBalance(
                product_id=product_id,
                location_id=location_id,
                quantity_on_hand=0,
                quantity_reserved=0,
                created_by_id=actor_user.id,
            )
            db.add(balance)
            await db.flush()

        # ------------------------------------
        # 3. Validate non-negative stock
        # ------------------------------------
        new_quantity = balance.quantity_on_hand + quantity_change
        if new_quantity < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient stock",
            )

        # ------------------------------------
        # 4. Insert movement (source of truth)
        # ------------------------------------
        movement = InventoryMovement(
            product_id=product_id,
            location_id=location_id,
            quantity_change=quantity_change,
            movement_type=movement_type,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by_id=actor_user.id,
        )
        db.add(movement)

        # ------------------------------------
        # 5. Update balance (derived)
        # ------------------------------------
        balance.quantity_on_hand = new_quantity
        balance.updated_by_id = actor_user.id

        await db.commit()

        # ------------------------------------
        # 6. Activity log (audit-grade)
        # ------------------------------------
        await emit_activity(
            db,
            user_id=actor_user.id,
            username=actor_user.username,
            code=ActivityCode.INVENTORY_MOVEMENT,
            actor_role=actor_user.role.capitalize(),
            actor_email=actor_user.username,
            product_id=product_id,
            location_id=location_id,
            movement_type=movement_type.value,
            quantity_change=quantity_change,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        return movement

    except HTTPException:
        await db.rollback()
        raise

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Concurrent inventory update detected",
        )

    except Exception:
        await db.rollback()
        raise
