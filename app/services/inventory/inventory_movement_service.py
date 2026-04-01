# app/services/inventory/inventory_movement_service.py
# ERP-017 FIXED: Added explicit product and location existence validation before creating
#                a balance row. Previously a missing product/location would produce an
#                IntegrityError (FK violation) with no helpful message; now it raises a
#                clean AppException first.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import noload

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.inventory_movement_models import InventoryMovement
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation
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
        raise AppException(400, "Inventory movement quantity cannot be zero", ErrorCode.VALIDATION_ERROR)

    if reference_type not in ALLOWED_REFERENCE_TYPES:
        raise AppException(400, "Invalid inventory reference type", ErrorCode.VALIDATION_ERROR)

    if movement_type in POSITIVE_MOVEMENTS and quantity_change < 0:
        raise AppException(400, f"{movement_type.value} must have positive quantity", ErrorCode.VALIDATION_ERROR)

    if movement_type in NEGATIVE_MOVEMENTS and quantity_change > 0:
        raise AppException(400, f"{movement_type.value} must have negative quantity", ErrorCode.VALIDATION_ERROR)

    try:
        # ------------------------------------
        # 1. Lock inventory balance row
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
        #    ERP-017 FIXED: Validate product and location BEFORE inserting.
        #    Previously this would produce an IntegrityError (FK violation) with
        #    no helpful message for the caller.
        # ------------------------------------
        if not balance:
            product_ok = await db.scalar(
                select(Product.id).where(
                    Product.id == product_id,
                    Product.is_deleted.is_(False),
                )
            )
            if not product_ok:
                raise AppException(
                    404,
                    f"Product {product_id} not found or has been deleted",
                    ErrorCode.PRODUCT_NOT_FOUND,
                )

            location_ok = await db.scalar(
                select(InventoryLocation.id).where(
                    InventoryLocation.id == location_id,
                    InventoryLocation.is_active.is_(True),
                    InventoryLocation.is_deleted.is_(False),
                )
            )
            if not location_ok:
                raise AppException(
                    404,
                    f"Inventory location {location_id} not found or is inactive",
                    ErrorCode.LOCATION_NOT_FOUND,
                )

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
            raise AppException(
                409,
                f"Insufficient stock: {balance.quantity} available, {abs(quantity_change)} requested",
                ErrorCode.INSUFFICIENT_STOCK,
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
        # 5. Update balance
        # ------------------------------------
        balance.quantity = new_quantity
        balance.updated_by_id = actor_user.id

        await db.flush()

        # ------------------------------------
        # 6. Activity log (NO COMMIT — caller commits)
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

    except AppException:
        raise

    except IntegrityError:
        raise AppException(
            409,
            "Concurrent inventory update detected — please retry",
            ErrorCode.CONCURRENT_UPDATE,
        )

    except Exception:
        raise
