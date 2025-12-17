from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc, delete, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import noload

from app.models.inventory.grn_models import GRN, GRNItem
from app.models.masters.product_models import Product
from app.models.masters.supplier_models import Supplier
from app.models.inventory.inventory_location_models import InventoryLocation
from app.models.users.user_models import User

from app.constants.grn import GRNStatus
from app.constants.inventory_movement_type import InventoryMovementType
from app.constants.activity_codes import ActivityCode
from app.constants.error_codes import ErrorCode

from app.core.exceptions import AppException
from app.services.inventory.inventory_movement_service import apply_inventory_movement
from app.utils.activity_helpers import emit_activity

from app.schemas.inventory.grn_schemas import (
    GRNCreateSchema,
    GRNUpdateSchema,
    GRNTableSchema,
)


# =====================================================
# SORT MAP
# =====================================================
ALLOWED_SORT_FIELDS = {
    "created_at": GRN.created_at,
    "status": GRN.status,
    "id": GRN.id,
}

import hashlib
import json
from decimal import Decimal


def generate_grn_item_signature(items: list[dict]) -> str:
    """
    Deterministic, order-independent GRN item signature.
    """

    normalized = [
        {
            "product_id": i["product_id"],
            "quantity": int(i["quantity"]),
            "unit_cost": str(Decimal(i["unit_cost"]).quantize(Decimal("0.01"))),
        }
        for i in items
    ]

    normalized.sort(key=lambda x: x["product_id"])

    payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()



# =====================================================
# MAPPER
# =====================================================
def _map_grn(grn: GRN) -> GRNTableSchema:
    return GRNTableSchema(
        id=grn.id,
        supplier_id=grn.supplier_id,
        location_id=grn.location_id,
        purchase_order=grn.purchase_order,
        bill_number=grn.bill_number,
        notes=grn.notes,
        status=grn.status,
        version=grn.version,
        created_at=grn.created_at,
        created_by=grn.created_by_id,
        updated_by=grn.updated_by_id,
        created_by_name=grn.created_by_username,
        updated_by_name=grn.updated_by_username,
        items=[
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_cost": i.unit_cost,
            }
            for i in grn.items
        ],
    )


# =====================================================
# CREATE
# =====================================================


async def create_grn(db: AsyncSession, payload: GRNCreateSchema, user: User) -> GRNTableSchema:
    if not payload.items:
        raise AppException(400, "GRN must contain at least one item", ErrorCode.GRN_EMPTY_ITEMS)

    supplier = await db.get(Supplier, payload.supplier_id)
    if not supplier or supplier.is_deleted:
        raise AppException(400, "Invalid supplier", ErrorCode.GRN_INVALID_SUPPLIER)

    location = await db.get(InventoryLocation, payload.location_id)
    if not location or location.is_deleted or not location.is_active:
        raise AppException(400, "Invalid location", ErrorCode.GRN_INVALID_LOCATION)

    if payload.bill_number:
        exists_bill = await db.scalar(
            select(GRN.id).where(
                GRN.bill_number == payload.bill_number,
                GRN.is_deleted.is_(False),
            )
        )
        if exists_bill:
            raise AppException(409, "Bill number already exists", ErrorCode.GRN_BILL_EXISTS)

    # ---------- ITEM SIGNATURE ----------
    signature = generate_grn_item_signature(
        [i.model_dump() for i in payload.items]
    )

    exists_signature = await db.scalar(
        select(GRN.id).where(
            GRN.item_signature == signature,
            GRN.is_deleted.is_(False),
        )
    )

    if exists_signature:
        raise AppException(
            409,
            "Duplicate GRN with same item composition already exists",
            ErrorCode.GRN_DUPLICATE_ITEMS,
        )

    try:
        grn = GRN(
            supplier_id=payload.supplier_id,
            location_id=payload.location_id,
            purchase_order=payload.purchase_order,
            bill_number=payload.bill_number,
            notes=payload.notes,
            status=GRNStatus.DRAFT,
            item_signature=signature,
            created_by_id=user.id,
        )

        db.add(grn)
        await db.flush()

        for item in payload.items:
            product = await db.get(Product, item.product_id)
            if not product or product.is_deleted:
                raise AppException(
                    400,
                    f"Invalid product {item.product_id}",
                    ErrorCode.GRN_INVALID_PRODUCT,
                )

            db.add(
                GRNItem(
                    grn_id=grn.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                )
            )

        await emit_activity(
            db=db,
            user_id=user.id,
            username=user.username,
            code=ActivityCode.CREATE_GRN,
            actor_role=user.role.capitalize(),
            actor_email=user.username,
            target_name=f"GRN {grn.id}",
        )

        await db.commit()
        await db.refresh(grn)

    except IntegrityError:
        await db.rollback()
        raise AppException(
            409,
            "Duplicate GRN detected",
            ErrorCode.GRN_DUPLICATE_ITEMS,
        )

    return _map_grn(grn)



# =====================================================
# GET
# =====================================================
async def get_grn(db: AsyncSession, grn_id: int) -> GRNTableSchema:
    grn = await db.get(GRN, grn_id)
    if not grn or grn.is_deleted:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)
    return _map_grn(grn)


# =====================================================
# LIST
# =====================================================
async def list_grns(
    db: AsyncSession,
    *,
    supplier_id: int | None,
    status: str | None,
    start_date: str | None,
    end_date: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
):
    base = select(GRN).where(GRN.is_deleted.is_(False))

    if supplier_id:
        base = base.where(GRN.supplier_id == supplier_id)
    if status:
        base = base.where(GRN.status == status)
    if start_date:
        base = base.where(GRN.created_at >= start_date)
    if end_date:
        base = base.where(GRN.created_at <= end_date)

    sort_col = ALLOWED_SORT_FIELDS.get(sort_by, GRN.created_at)
    sort_order = desc(sort_col) if order.lower() == "desc" else asc(sort_col)

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.execute(
        base.order_by(sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return total or 0, [_map_grn(g) for g in rows.scalars().all()]



async def update_grn(
    db: AsyncSession,
    grn_id: int,
    payload: GRNUpdateSchema,
    user: User,
) -> GRNTableSchema:

    result = await db.execute(
        select(GRN)
        .where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
            GRN.version == payload.version,
        )
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(
            409,
            "GRN modified by another process",
            ErrorCode.GRN_VERSION_CONFLICT,
        )

    if grn.status != GRNStatus.DRAFT:
        raise AppException(
            400,
            "Only draft GRNs can be updated",
            ErrorCode.GRN_INVALID_STATUS,
        )

    changes: list[str] = []

    # ---------------- SUPPLIER ----------------
    if payload.supplier_id is not None and payload.supplier_id != grn.supplier_id:
        supplier = await db.get(Supplier, payload.supplier_id)
        if not supplier or supplier.is_deleted:
            raise AppException(
                400,
                "Invalid supplier",
                ErrorCode.GRN_INVALID_SUPPLIER,
            )
        grn.supplier_id = payload.supplier_id
        changes.append("supplier_id")

    # ---------------- LOCATION ----------------
    if payload.location_id is not None and payload.location_id != grn.location_id:
        location = await db.get(InventoryLocation, payload.location_id)
        if not location or location.is_deleted or not location.is_active:
            raise AppException(
                400,
                "Invalid location",
                ErrorCode.GRN_INVALID_LOCATION,
            )
        grn.location_id = payload.location_id
        changes.append("location_id")

    # ---------------- BILL NUMBER ----------------
    if payload.bill_number is not None and payload.bill_number != grn.bill_number:
        exists = await db.scalar(
            select(GRN.id).where(
                GRN.bill_number == payload.bill_number,
                GRN.id != grn.id,
                GRN.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(
                409,
                "Bill number already exists",
                ErrorCode.GRN_BILL_EXISTS,
            )
        grn.bill_number = payload.bill_number
        changes.append("bill_number")

    # ---------------- PURCHASE ORDER ----------------
    if payload.purchase_order is not None:
        grn.purchase_order = payload.purchase_order
        changes.append("purchase_order")

    # ---------------- NOTES ----------------
    if payload.notes is not None:
        grn.notes = payload.notes
        changes.append("notes")

    # =====================================================
    # ITEMS (OPTIONAL)
    # =====================================================
    if payload.items is not None:

        if not payload.items:
            raise AppException(
                400,
                "GRN must contain at least one item",
                ErrorCode.GRN_EMPTY_ITEMS,
            )

        # ---------- recompute signature ----------
        new_signature = generate_grn_item_signature(
            [i.model_dump() for i in payload.items]
        )

        if new_signature != grn.item_signature:
            exists_signature = await db.scalar(
                select(GRN.id).where(
                    GRN.item_signature == new_signature,
                    GRN.id != grn.id,
                    GRN.is_deleted.is_(False),
                )
            )
            if exists_signature:
                raise AppException(
                    409,
                    "Another GRN with same item composition already exists",
                    ErrorCode.GRN_DUPLICATE_ITEMS,
                )

            grn.item_signature = new_signature
            changes.append("items")

        # ---------- replace items ----------
        await db.execute(
            delete(GRNItem).where(GRNItem.grn_id == grn.id)
        )

        for item in payload.items:
            product = await db.get(Product, item.product_id)
            if not product or product.is_deleted:
                raise AppException(
                    400,
                    f"Invalid product {item.product_id}",
                    ErrorCode.GRN_INVALID_PRODUCT,
                )

            db.add(
                GRNItem(
                    grn_id=grn.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                )
            )

    if not changes:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.NO_CHANGES_DETECTED,
        )

    grn.version += 1
    grn.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_GRN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=f"GRN {grn.id}",
        changes=", ".join(changes),
    )

    await db.commit()
    await db.refresh(grn)

    return _map_grn(grn)



async def verify_grn(
    db: AsyncSession,
    grn_id: int,
    user: User,
) -> GRNTableSchema:

    result = await db.execute(
        select(GRN)
        .where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
        )
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)

    if grn.status != GRNStatus.DRAFT:
        raise AppException(
            409,
            "GRN already processed",
            ErrorCode.GRN_INVALID_STATUS,
        )

    items = (
        await db.execute(select(GRNItem).where(GRNItem.grn_id == grn.id))
    ).scalars().all()

    if not items:
        raise AppException(
            400,
            "GRN has no items",
            ErrorCode.GRN_EMPTY_ITEMS,
        )

    for item in items:
        await apply_inventory_movement(
            db=db,
            product_id=item.product_id,
            location_id=grn.location_id,
            quantity_change=item.quantity,
            movement_type=InventoryMovementType.STOCK_IN,
            reference_type="GRN",
            reference_id=grn.id,
            actor_user=user,
        )

    grn.status = GRNStatus.VERIFIED
    grn.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.VERIFY_GRN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=f"GRN {grn.id}",
    )

    await db.commit()
    await db.refresh(grn)

    return _map_grn(grn)

async def delete_grn(
    db: AsyncSession,
    grn_id: int,
    user: User,
) -> GRNTableSchema:

    grn = await db.get(GRN, grn_id)
    if not grn or grn.is_deleted:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)

    if grn.status != GRNStatus.DRAFT:
        raise AppException(
            409,
            "Verified GRN cannot be deleted",
            ErrorCode.GRN_INVALID_STATUS,
        )

    grn.is_deleted = True
    grn.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DELETE_GRN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=f"GRN {grn.id}",
    )

    await db.commit()
    return _map_grn(grn)
