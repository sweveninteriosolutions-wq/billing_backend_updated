from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import noload
from fastapi import HTTPException, status

from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.inventory_movement_models import InventoryMovement
from app.constants.inventory_movement_type import InventoryMovementType
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
    # 0. Basic validations
    # ------------------------------------
    if quantity_change == 0:
        raise HTTPException(400, "Inventory movement quantity cannot be zero")

    if reference_type not in ALLOWED_REFERENCE_TYPES:
        raise HTTPException(400, "Invalid inventory reference type")

    if movement_type in POSITIVE_MOVEMENTS and quantity_change < 0:
        raise HTTPException(
            400, f"{movement_type.value} must have positive quantity"
        )

    if movement_type in NEGATIVE_MOVEMENTS and quantity_change > 0:
        raise HTTPException(
            400, f"{movement_type.value} must have negative quantity"
        )

    try:
        # ------------------------------------
        # 1. Lock inventory balance row (NO JOINS)
        # ------------------------------------
        result = await db.execute(
            select(InventoryBalance)
            .options(noload("*"))
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
                quantity=0,
                created_by_id=actor_user.id,
            )
            db.add(balance)
            await db.flush()

        # ------------------------------------
        # 3. Validate non-negative stock
        # ------------------------------------
        new_quantity = balance.quantity + quantity_change
        if new_quantity < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient stock",
            )

        # ------------------------------------
        # 4. Insert inventory movement (ledger)
        # ------------------------------------
        db.add(
            InventoryMovement(
                product_id=product_id,
                location_id=location_id,
                quantity_change=quantity_change,
                reference_type=reference_type,
                reference_id=reference_id,
                created_by_id=actor_user.id,
            )
        )

        # ------------------------------------
        # 5. Update balance (derived)
        # ------------------------------------
        balance.quantity = new_quantity
        balance.updated_by_id = actor_user.id

        await db.flush() 

        # ------------------------------------
        # 6. Activity log (NO COMMIT HERE)
        # ------------------------------------
        await emit_activity(
            db,
            user_id=actor_user.id,
            username=actor_user.username,
            code=ActivityCode.INVENTORY_MOVEMENT,
            actor_role=actor_user.role.capitalize(),
            actor_email=actor_user.username,
            movement_type=movement_type.value,
            quantity_change=quantity_change,
            product_id=product_id,
            location_id=location_id,
            reference_type=reference_type,
            reference_id=reference_id,
        )

        return True

    except HTTPException:
        raise

    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Concurrent inventory update detected",
        )

    except Exception:
        raise
