from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc, delete
from sqlalchemy.exc import IntegrityError

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
    GRNListData,
)

import hashlib
import json
from decimal import Decimal


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
            "unit_cost": str(
                Decimal(i["unit_cost"]).quantize(Decimal("0.01"))
            ),
        }
        for i in items
    ]
    normalized.sort(key=lambda x: x["product_id"])
    payload = json.dumps(normalized, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


# =====================================================
# SHARED ITEM FETCH
# =====================================================
async def _fetch_grn_items(db: AsyncSession, grn_id: int):
    rows = await db.execute(
        select(GRNItem).where(GRNItem.grn_id == grn_id)
    )
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

    # -------------------------
    # ITEMS CHECK
    # -------------------------
    if not payload.items:
        raise AppException(
            400,
            "GRN must contain at least one item",
            ErrorCode.GRN_EMPTY_ITEMS,
        )

    # -------------------------
    # SUPPLIER VALIDATION
    # -------------------------
    row = await db.execute(
        select(Supplier.id, Supplier.is_deleted)
        .where(Supplier.id == payload.supplier_id)
    )
    supplier = row.first()

    if not supplier or supplier.is_deleted:
        raise AppException(
            400,
            "Invalid supplier",
            ErrorCode.GRN_INVALID_SUPPLIER,
        )

    # -------------------------
    # LOCATION VALIDATION
    # -------------------------
    row = await db.execute(
        select(
            InventoryLocation.is_deleted,
            InventoryLocation.is_active,
        )
        .where(InventoryLocation.id == payload.location_id)
    )
    loc = row.first()

    if not loc or loc.is_deleted or not loc.is_active:
        raise AppException(
            400,
            "Invalid location",
            ErrorCode.GRN_INVALID_LOCATION,
        )

    # -------------------------
    # BILL NUMBER CHECK
    # -------------------------
    if payload.bill_number:
        exists_bill = await db.scalar(
            select(GRN.id).where(
                GRN.bill_number == payload.bill_number,
                GRN.is_deleted.is_(False),
            )
        )
        if exists_bill:
            raise AppException(
                409,
                "Bill number already exists",
                ErrorCode.GRN_BILL_EXISTS,
            )

    # -------------------------
    # ITEM SIGNATURE
    # -------------------------
    signature = generate_grn_item_signature(
        [i.model_dump() for i in payload.items]
    )

    # -------------------------
    # SIGNATURE DUPLICATE CHECK
    # -------------------------
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

    # -------------------------
    # BULK PRODUCT VALIDATION
    # -------------------------
    product_ids = {i.product_id for i in payload.items}

    rows = await db.execute(
        select(Product.id).where(
            Product.id.in_(product_ids),
            Product.is_deleted.is_(False),
        )
    )
    valid_product_ids = set(rows.scalars().all())

    invalid_products = product_ids - valid_product_ids
    if invalid_products:
        raise AppException(
            400,
            f"Invalid product(s): {sorted(invalid_products)}",
            ErrorCode.GRN_INVALID_PRODUCT,
        )

    # -------------------------
    # CREATE GRN + ITEMS
    # -------------------------
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

        db.add_all(
            [
                GRNItem(
                    grn_id=grn.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                )
                for item in payload.items
            ]
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

    except IntegrityError:
        await db.rollback()
        raise AppException(
            409,
            "Duplicate GRN detected",
            ErrorCode.GRN_DUPLICATE_ITEMS,
        )

    # -------------------------
    # RESPONSE (NO ORM LAZY LOAD)
    # -------------------------
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
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_cost": i.unit_cost,
            }
            for i in payload.items
        ],
    )

# =====================================================
# GET
# =====================================================
from sqlalchemy.orm import selectinload

async def get_grn(
    db: AsyncSession,
    grn_id: int,
) -> GRNOutSchema:

    result = await db.execute(
        select(GRN)
        .options(
            selectinload(GRN.items),        # preload items
            selectinload(GRN.created_by),   # preload user for hybrid
            selectinload(GRN.updated_by),   # preload user for hybrid
        )
        .where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
        )
    )

    grn = result.scalar_one_or_none()

    if not grn:
        raise AppException(
            404,
            "GRN not found",
            ErrorCode.GRN_NOT_FOUND,
        )

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
        created_by_name=grn.created_by_username,  # ✅ safe now
        updated_by_name=grn.updated_by_username,  # ✅ safe now
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
# LIST
# =====================================================
from sqlalchemy.orm import selectinload

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
) -> GRNListData:

    base = (
        select(GRN)
        .options(
            selectinload(GRN.items),        # preload items
            selectinload(GRN.created_by),   # needed for hybrid
            selectinload(GRN.updated_by),   # needed for hybrid
        )
        .where(GRN.is_deleted.is_(False))
    )

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

    # -------------------------
    # TOTAL COUNT (cheap)
    # -------------------------
    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    # -------------------------
    # FETCH PAGE
    # -------------------------
    rows = await db.execute(
        base.order_by(sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    grns = rows.scalars().all()

    # -------------------------
    # BUILD RESPONSE (NO DB HITS)
    # -------------------------
    items = [
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
            created_by_name=grn.created_by_username,  # hybrid OK
            updated_by_name=grn.updated_by_username,  # hybrid OK
            items=[
                {
                    "product_id": i.product_id,
                    "quantity": i.quantity,
                    "unit_cost": i.unit_cost,
                }
                for i in grn.items
            ],
        )
        for grn in grns
    ]

    return GRNListData(
        total=total or 0,
        items=items,
    )

from sqlalchemy import select, func
from app.models.inventory.grn_models import GRN, GRNItem
from app.models.masters.supplier_models import Supplier


async def list_grns_summary(
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
    filters = [GRN.is_deleted.is_(False)]

    if supplier_id:
        filters.append(GRN.supplier_id == supplier_id)

    if status:
        filters.append(GRN.status == status)

    if start_date:
        filters.append(GRN.created_at >= start_date)

    if end_date:
        filters.append(GRN.created_at <= end_date)

    total = await db.scalar(
        select(func.count())
        .select_from(GRN)
        .where(*filters)
    )

    order_col = GRN.created_at.desc() if order == "desc" else GRN.created_at.asc()

    result = await db.execute(
        select(
            GRN.id.label("grn_code"),
            Supplier.name.label("supplier_name"),
            GRN.purchase_order,
            func.count(GRNItem.id).label("no_of_items"),
            func.coalesce(
                func.sum(GRNItem.quantity * GRNItem.unit_cost), 0
            ).label("total_grn_value"),
            GRN.created_at,
            GRN.status,
        )
        .join(Supplier, Supplier.id == GRN.supplier_id)
        .outerjoin(GRNItem, GRNItem.grn_id == GRN.id)
        .where(*filters)
        .group_by(
            GRN.id,
            Supplier.name,
            GRN.purchase_order,
            GRN.created_at,
            GRN.status,
        )
        .order_by(order_col)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = result.all()

    items = [
        {
            "grn_code": r.grn_code,
            "supplier_name": r.supplier_name,
            "purchase_order": r.purchase_order,
            "no_of_items": r.no_of_items,
            "total_grn_value": r.total_grn_value,
            "created_at": r.created_at,
            "status": r.status,
        }
        for r in rows
    ]

    return {
        "total": total or 0,
        "items": items,
    }


async def update_grn(
    db: AsyncSession,
    grn_id: int,
    payload: GRNUpdateSchema,
    user: User,
) -> GRNOutSchema:

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

    # -------- supplier --------
    if payload.supplier_id is not None and payload.supplier_id != grn.supplier_id:
        row = await db.execute(
            select(Supplier.is_deleted).where(Supplier.id == payload.supplier_id)
        )
        is_deleted = row.scalar()
        if is_deleted is None or is_deleted:
            raise AppException(400, "Invalid supplier", ErrorCode.GRN_INVALID_SUPPLIER)

        grn.supplier_id = payload.supplier_id
        changes.append("supplier_id")

    # -------- location --------
    if payload.location_id is not None and payload.location_id != grn.location_id:
        row = await db.execute(
            select(
                InventoryLocation.is_deleted,
                InventoryLocation.is_active,
            )
            .where(InventoryLocation.id == payload.location_id)
        )
        loc = row.first()
        if not loc or loc.is_deleted or not loc.is_active:
            raise AppException(400, "Invalid location", ErrorCode.GRN_INVALID_LOCATION)

        grn.location_id = payload.location_id
        changes.append("location_id")

    # -------- bill number --------
    if payload.bill_number is not None and payload.bill_number != grn.bill_number:
        exists = await db.scalar(
            select(GRN.id).where(
                GRN.bill_number == payload.bill_number,
                GRN.id != grn.id,
                GRN.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(409, "Bill number already exists", ErrorCode.GRN_BILL_EXISTS)

        grn.bill_number = payload.bill_number
        changes.append("bill_number")

    # -------- purchase order --------
    if payload.purchase_order is not None:
        grn.purchase_order = payload.purchase_order
        changes.append("purchase_order")

    # -------- notes --------
    if payload.notes is not None:
        grn.notes = payload.notes
        changes.append("notes")

    # -------- items --------
    if payload.items is not None:
        if not payload.items:
            raise AppException(400, "GRN must contain at least one item", ErrorCode.GRN_EMPTY_ITEMS)

        new_signature = generate_grn_item_signature(
            [i.model_dump() for i in payload.items]
        )

        if new_signature != grn.item_signature:
            exists = await db.scalar(
                select(GRN.id).where(
                    GRN.item_signature == new_signature,
                    GRN.id != grn.id,
                    GRN.is_deleted.is_(False),
                )
            )
            if exists:
                raise AppException(
                    409,
                    "Another GRN with same item composition already exists",
                    ErrorCode.GRN_DUPLICATE_ITEMS,
                )

            grn.item_signature = new_signature
            changes.append("items")

        # bulk product validation
        product_ids = {i.product_id for i in payload.items}
        rows = await db.execute(
            select(Product.id).where(
                Product.id.in_(product_ids),
                Product.is_deleted.is_(False),
            )
        )
        if missing := product_ids - set(rows.scalars().all()):
            raise AppException(
                400,
                f"Invalid product(s): {sorted(missing)}",
                ErrorCode.GRN_INVALID_PRODUCT,
            )

        await db.execute(delete(GRNItem).where(GRNItem.grn_id == grn.id))

        db.add_all(
            [
                GRNItem(
                    grn_id=grn.id,
                    product_id=i.product_id,
                    quantity=i.quantity,
                    unit_cost=i.unit_cost,
                )
                for i in payload.items
            ]
        )

    if not changes:
        raise AppException(400, "No changes detected", ErrorCode.NO_CHANGES_DETECTED)

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

    return await get_grn(db, grn.id)


async def verify_grn(
    db: AsyncSession,
    grn_id: int,
    user: User,
) -> GRNOutSchema:

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

    items = await _fetch_grn_items(db, grn.id)
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
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.VERIFY_GRN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=f"GRN {grn.id}",
    )

    await db.commit()

    return _build_grn_out(grn, items)

async def delete_grn(
    db: AsyncSession,
    grn_id: int,
    user: User,
) -> GRNOutSchema:

    row = await db.execute(
        select(GRN).where(GRN.id == grn_id, GRN.is_deleted.is_(False))
    )
    grn = row.scalar_one_or_none()

    if not grn:
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

    return _build_grn_out(grn, grn.items)
