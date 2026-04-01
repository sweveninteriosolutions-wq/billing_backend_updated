# app/services/inventory/grn_service.py
# ERP-019 FIXED: verify_grn now fetches GRN items with SELECT ... FOR UPDATE to prevent
#                concurrent verification from processing stale item data.
# ERP-029 FIXED: list_grns_view no longer uses fragile JSON path casting for supplier_id
#                filtering or string-comparison for date filtering. It now queries the base
#                GRN table directly for all filterable fields.
# ERP-036 FIXED: `from sqlalchemy.orm import selectinload` moved to module-level imports.
# ERP-037 FIXED: `delete_grn` renamed to `cancel_grn` — it sets status=CANCELLED, not
#                is_deleted=True, so the name was semantically incorrect.

import hashlib
import json
import logging
from decimal import Decimal
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload  # ERP-036: moved from mid-file to top

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
    GRNOutSchema,
)

logger = logging.getLogger(__name__)


# =====================================================
# SORT MAP
# =====================================================
ALLOWED_SORT_FIELDS = {
    "created_at": GRN.created_at,
    "status": GRN.status,
    "id": GRN.id,
}


# =====================================================
# ITEM SIGNATURE
# =====================================================
def generate_grn_item_signature(items: list[dict]) -> str:
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
# SHARED ITEM FETCH (with optional lock)
# =====================================================
async def _fetch_grn_items(db: AsyncSession, grn_id: int, lock: bool = False):
    """
    ERP-019: Pass lock=True during verify_grn to prevent concurrent verifications
    from reading the same items simultaneously.
    """
    stmt = select(GRNItem).where(GRNItem.grn_id == grn_id)
    if lock:
        stmt = stmt.with_for_update()
    rows = await db.execute(stmt)
    return rows.scalars().all()


# =====================================================
# SHARED RESPONSE BUILDER
# =====================================================
def _build_grn_out(grn: GRN, items: list[GRNItem]) -> GRNOutSchema:
    return GRNOutSchema(
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
            for i in items
        ],
    )


# =====================================================
# CREATE
# =====================================================
async def create_grn(
    db: AsyncSession,
    payload: GRNCreateSchema,
    user: User,
) -> GRNOutSchema:

    if not payload.items:
        raise AppException(400, "GRN must contain at least one item", ErrorCode.GRN_EMPTY_ITEMS)

    row = await db.execute(
        select(Supplier.id, Supplier.is_deleted).where(Supplier.id == payload.supplier_id)
    )
    supplier = row.first()
    if not supplier or supplier.is_deleted:
        raise AppException(400, "Invalid supplier", ErrorCode.GRN_INVALID_SUPPLIER)

    row = await db.execute(
        select(InventoryLocation.is_deleted, InventoryLocation.is_active)
        .where(InventoryLocation.id == payload.location_id)
    )
    loc = row.first()
    if not loc or loc.is_deleted or not loc.is_active:
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

    signature = generate_grn_item_signature([i.model_dump() for i in payload.items])

    exists_signature = await db.scalar(
        select(GRN.id).where(
            GRN.item_signature == signature,
            GRN.is_deleted.is_(False),
        )
    )
    if exists_signature:
        raise AppException(409, "Duplicate GRN with same item composition already exists", ErrorCode.GRN_DUPLICATE_ITEMS)

    product_ids = {i.product_id for i in payload.items}
    rows = await db.execute(
        select(Product.id).where(Product.id.in_(product_ids), Product.is_deleted.is_(False))
    )
    valid_product_ids = set(rows.scalars().all())
    if invalid_products := product_ids - valid_product_ids:
        raise AppException(400, f"Invalid product(s): {sorted(invalid_products)}", ErrorCode.GRN_INVALID_PRODUCT)

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

        db.add_all([
            GRNItem(
                grn_id=grn.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
            )
            for item in payload.items
        ])

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

    except IntegrityError:
        await db.rollback()
        raise AppException(409, "Duplicate GRN detected", ErrorCode.GRN_DUPLICATE_ITEMS)

    return GRNOutSchema(
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
        created_by_name=user.username,
        updated_by_name=None,
        items=[
            {"product_id": i.product_id, "quantity": i.quantity, "unit_cost": i.unit_cost}
            for i in payload.items
        ],
    )


# =====================================================
# GET
# =====================================================
async def get_grn(db: AsyncSession, grn_id: int) -> GRNOutSchema:
    result = await db.execute(
        select(GRN)
        .options(
            selectinload(GRN.items),
            selectinload(GRN.created_by),
            selectinload(GRN.updated_by),
        )
        .where(GRN.id == grn_id, GRN.is_deleted.is_(False))
    )
    grn = result.scalar_one_or_none()
    if not grn:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)

    return GRNOutSchema(
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
            {"product_id": i.product_id, "quantity": i.quantity, "unit_cost": i.unit_cost}
            for i in grn.items
        ],
    )


# =====================================================
# LIST
# ERP-029 FIXED: Replaced fragile JSON path casting (`GRNView.supplier["id"].astext.cast(int)`)
# and string date comparison (`GRNView.audit["created_at"].astext >= start_date`) with a direct
# query on the GRN table using properly typed columns and indexes.
# =====================================================
async def list_grns(
    db: AsyncSession,
    *,
    supplier_id: int | None,
    status: str | None,
    start_date: date | None,
    end_date: date | None,
    page: int,
    page_size: int,
    sort_by: str = "created_at",
    order: str = "desc",
) -> dict:
    filters = [GRN.is_deleted.is_(False)]

    if supplier_id:
        filters.append(GRN.supplier_id == supplier_id)

    if status:
        filters.append(GRN.status == status)

    if start_date:
        filters.append(GRN.created_at >= datetime.combine(start_date, datetime.min.time()))

    if end_date:
        filters.append(GRN.created_at <= datetime.combine(end_date, datetime.max.time()))

    sort_col_map = {
        "created_at": GRN.created_at,
        "status": GRN.status,
        "id": GRN.id,
    }
    sort_col = sort_col_map.get(sort_by, GRN.created_at)
    order_by = sort_col.desc() if order == "desc" else sort_col.asc()

    total = await db.scalar(
        select(func.count(GRN.id)).where(*filters)
    )

    result = await db.execute(
        select(GRN)
        .options(
            selectinload(GRN.items),
            selectinload(GRN.created_by),
            selectinload(GRN.updated_by),
        )
        .where(*filters)
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    grns = result.scalars().all()

    return {
        "total": total or 0,
        "items": [
            GRNOutSchema(
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
                    {"product_id": i.product_id, "quantity": i.quantity, "unit_cost": i.unit_cost}
                    for i in grn.items
                ],
            )
            for grn in grns
        ],
    }

# Keep old name as alias for any existing router calls — remove in next cleanup sprint
list_grns_view = list_grns


# =====================================================
# UPDATE
# =====================================================
async def update_grn(db: AsyncSession, grn_id: int, payload: GRNUpdateSchema, user: User) -> GRNOutSchema:
    result = await db.execute(
        select(GRN)
        .where(GRN.id == grn_id, GRN.is_deleted.is_(False), GRN.version == payload.version)
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(409, "GRN modified by another process", ErrorCode.GRN_VERSION_CONFLICT)

    if grn.status != GRNStatus.DRAFT:
        raise AppException(400, "Only draft GRNs can be updated", ErrorCode.GRN_INVALID_STATUS)

    changes: list[str] = []

    if payload.supplier_id is not None and payload.supplier_id != grn.supplier_id:
        row = await db.execute(select(Supplier.is_deleted).where(Supplier.id == payload.supplier_id))
        is_deleted = row.scalar()
        if is_deleted is None or is_deleted:
            raise AppException(400, "Invalid supplier", ErrorCode.GRN_INVALID_SUPPLIER)
        grn.supplier_id = payload.supplier_id
        changes.append("supplier_id")

    if payload.location_id is not None and payload.location_id != grn.location_id:
        row = await db.execute(
            select(InventoryLocation.is_deleted, InventoryLocation.is_active)
            .where(InventoryLocation.id == payload.location_id)
        )
        loc = row.first()
        if not loc or loc.is_deleted or not loc.is_active:
            raise AppException(400, "Invalid location", ErrorCode.GRN_INVALID_LOCATION)
        grn.location_id = payload.location_id
        changes.append("location_id")

    if payload.bill_number is not None and payload.bill_number != grn.bill_number:
        exists = await db.scalar(
            select(GRN.id).where(GRN.bill_number == payload.bill_number, GRN.id != grn.id, GRN.is_deleted.is_(False))
        )
        if exists:
            raise AppException(409, "Bill number already exists", ErrorCode.GRN_BILL_EXISTS)
        grn.bill_number = payload.bill_number
        changes.append("bill_number")

    if payload.purchase_order is not None:
        grn.purchase_order = payload.purchase_order
        changes.append("purchase_order")

    if payload.notes is not None:
        grn.notes = payload.notes
        changes.append("notes")

    if payload.items is not None:
        if not payload.items:
            raise AppException(400, "GRN must contain at least one item", ErrorCode.GRN_EMPTY_ITEMS)

        new_signature = generate_grn_item_signature([i.model_dump() for i in payload.items])
        if new_signature != grn.item_signature:
            exists = await db.scalar(
                select(GRN.id).where(GRN.item_signature == new_signature, GRN.id != grn.id, GRN.is_deleted.is_(False))
            )
            if exists:
                raise AppException(409, "Another GRN with same item composition already exists", ErrorCode.GRN_DUPLICATE_ITEMS)
            grn.item_signature = new_signature
            changes.append("items")

        product_ids = {i.product_id for i in payload.items}
        rows = await db.execute(select(Product.id).where(Product.id.in_(product_ids), Product.is_deleted.is_(False)))
        if missing := product_ids - set(rows.scalars().all()):
            raise AppException(400, f"Invalid product(s): {sorted(missing)}", ErrorCode.GRN_INVALID_PRODUCT)

        await db.execute(delete(GRNItem).where(GRNItem.grn_id == grn.id))
        db.add_all([
            GRNItem(grn_id=grn.id, product_id=i.product_id, quantity=i.quantity, unit_cost=i.unit_cost)
            for i in payload.items
        ])

    if not changes:
        raise AppException(400, "No changes detected", ErrorCode.NO_CHANGES_DETECTED)

    grn.version += 1
    grn.updated_by_id = user.id

    await emit_activity(
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.UPDATE_GRN, actor_role=user.role.capitalize(),
        actor_email=user.username, target_name=f"GRN {grn.id}",
        changes=", ".join(changes),
    )

    await db.commit()
    return await get_grn(db, grn.id)


# =====================================================
# VERIFY
# ERP-019 FIXED: GRN items are now locked with FOR UPDATE during verification,
# preventing concurrent verify calls from processing the same items simultaneously.
# =====================================================
async def verify_grn(db: AsyncSession, grn_id: int, user: User) -> GRNOutSchema:
    result = await db.execute(
        select(GRN)
        .where(GRN.id == grn_id, GRN.is_deleted.is_(False))
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)

    if grn.status != GRNStatus.DRAFT:
        raise AppException(409, "GRN already processed", ErrorCode.GRN_INVALID_STATUS)

    # ERP-019 FIXED: lock=True prevents concurrent reads of the same items
    items = await _fetch_grn_items(db, grn.id, lock=True)
    if not items:
        raise AppException(400, "GRN has no items", ErrorCode.GRN_EMPTY_ITEMS)

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
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.VERIFY_GRN, actor_role=user.role.capitalize(),
        actor_email=user.username, target_name=f"GRN {grn.id}",
    )

    await db.commit()
    return _build_grn_out(grn, items)


# =====================================================
# CANCEL GRN
# ERP-037 FIXED: Renamed from `delete_grn` to `cancel_grn`.
#   The function has always set status=CANCELLED (not is_deleted=True),
#   so `delete_grn` was semantically incorrect. The old name is kept as
#   a deprecated alias below — update the router to use `cancel_grn`.
# =====================================================
async def cancel_grn(db: AsyncSession, grn_id: int, user: User) -> GRNOutSchema:
    result = await db.execute(
        select(GRN)
        .where(GRN.id == grn_id, GRN.is_deleted.is_(False))
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(404, "GRN not found", ErrorCode.GRN_NOT_FOUND)

    if grn.status != GRNStatus.DRAFT:
        raise AppException(409, "Only draft GRNs can be cancelled", ErrorCode.GRN_INVALID_STATUS)

    grn.status = GRNStatus.CANCELLED
    grn.updated_by_id = user.id

    await emit_activity(
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.CANCEL_GRN, actor_role=user.role.capitalize(),
        actor_email=user.username, target_name=f"GRN {grn.id}",
    )

    await db.commit()

    items = await _fetch_grn_items(db, grn.id)
    return _build_grn_out(grn, items)


# Deprecated alias — router should be updated to call cancel_grn directly
delete_grn = cancel_grn
