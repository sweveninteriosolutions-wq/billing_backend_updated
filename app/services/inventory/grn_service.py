from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists, func, asc, desc, delete
from fastapi import HTTPException, status
from sqlalchemy.orm import noload


from app.models.inventory.grn_models import GRN, GRNItem
from app.models.masters.product_models import Product
from app.models.masters.supplier_models import Supplier

from app.constants.grn import GRNStatus
from app.constants.inventory_movement_type import InventoryMovementType
from app.constants.activity_codes import ActivityCode

from app.services.inventory.inventory_movement_service import apply_inventory_movement
from app.utils.activity_helpers import emit_activity
from app.schemas.inventory.grn_schemas import GRNTableSchema, GRNUpdateSchema

ALLOWED_SORT_FIELDS = {
    "created_at": GRN.created_at,
    "status": GRN.status,
    "id": GRN.id,
}

def _map_grn(grn: GRN) -> GRNTableSchema:
    return GRNTableSchema(
        id=grn.id,
        supplier_id=grn.supplier_id,
        purchase_order=grn.purchase_order,
        bill_number=grn.bill_number,
        notes=grn.notes,
        status=grn.status,
        created_at=grn.created_at,
        created_by=grn.created_by_id,
        updated_by=grn.updated_by_id,
        created_by_name=grn.created_by_username,   # ✅ from hybrid_property
        updated_by_name=grn.updated_by_username,   # ✅ from hybrid_property
        version=grn.version,

        items=[
            {
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_cost": i.unit_cost,
            }
            for i in grn.items
        ],
    )

async def create_grn(
    db: AsyncSession,
    payload,
    current_user,
):
    supplier = await db.get(Supplier, payload.supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(400, "Invalid or inactive supplier")

    if not payload.items:
        raise HTTPException(400, "GRN must contain at least one item")

    if payload.bill_number:
        exists_bill = await db.scalar(
            select(exists().where(
                GRN.bill_number == payload.bill_number,
                GRN.is_deleted.is_(False),
            ))
        )
        if exists_bill:
            raise HTTPException(409, "Bill number already exists")

    grn = GRN(
        supplier_id=payload.supplier_id,
        purchase_order=payload.purchase_order,
        bill_number=payload.bill_number,
        notes=payload.notes,
        status=GRNStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(grn)
    await db.flush()

    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if not product or product.is_deleted:
            raise HTTPException(400, f"Invalid product {item.product_id}")

        db.add(GRNItem(
            grn_id=grn.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_cost=item.unit_cost,
        ))

    await db.commit()
    await db.refresh(grn)

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_GRN,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=f"GRN {grn.id}",
    )

    return _map_grn(grn)

async def get_grn(db: AsyncSession, grn_id: int):
    grn = await db.get(GRN, grn_id)
    if not grn or grn.is_deleted:
        raise HTTPException(404, "GRN not found")

    return _map_grn(grn)

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

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, GRN.created_at)
    sort_order = desc(sort_column) if order.lower() == "desc" else asc(sort_column)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(
        base.order_by(sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    grns = result.scalars().all()

    return total, [_map_grn(g) for g in grns]
async def update_grn(
    db: AsyncSession,
    grn_id: int,
    payload: GRNUpdateSchema,
    current_user,
):
    # ----------------------------------
    # Fetch + optimistic lock (NO JOINS)
    # ----------------------------------
    result = await db.execute(
        select(GRN)
        .options(noload("*"))
        .where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
            GRN.version == payload.version,
        )
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GRN was modified by another process",
        )

    if grn.status != GRNStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Only draft GRNs can be updated",
        )

    # ----------------------------------
    # Track changes for audit
    # ----------------------------------
    changes: list[str] = []

    # ----------------------------------
    # Supplier validation (if changed)
    # ----------------------------------
    if payload.supplier_id is not None and payload.supplier_id != grn.supplier_id:
        supplier = await db.get(Supplier, payload.supplier_id)
        if not supplier or supplier.is_deleted:
            raise HTTPException(400, "Invalid or inactive supplier")

        grn.supplier_id = payload.supplier_id
        changes.append(f"supplier → {payload.supplier_id}")

    # ----------------------------------
    # Bill number uniqueness
    # ----------------------------------
    if payload.bill_number and payload.bill_number != grn.bill_number:
        exists_bill = await db.scalar(
            select(exists().where(
                GRN.bill_number == payload.bill_number,
                GRN.is_deleted.is_(False),
                GRN.id != grn_id,
            ))
        )
        if exists_bill:
            raise HTTPException(409, "Bill number already exists")

        grn.bill_number = payload.bill_number
        changes.append(f"bill_number → {payload.bill_number}")

    # ----------------------------------
    # Update header fields (safe)
    # ----------------------------------
    if payload.purchase_order is not None:
        grn.purchase_order = payload.purchase_order
        changes.append("purchase_order updated")

    if payload.notes is not None:
        grn.notes = payload.notes
        changes.append("notes updated")

    # ----------------------------------
    # Replace items (atomic + safe)
    # ----------------------------------
    if not payload.items:
        raise HTTPException(400, "GRN must contain at least one item")

    await db.execute(
        delete(GRNItem).where(GRNItem.grn_id == grn_id)
    )

    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if not product or product.is_deleted:
            raise HTTPException(
                400, f"Invalid or inactive product {item.product_id}"
            )

        db.add(
            GRNItem(
                grn_id=grn.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_cost=item.unit_cost,
            )
        )

    changes.append(f"{len(payload.items)} items replaced")

    # ----------------------------------
    # Version bump + audit
    # ----------------------------------
    grn.version += 1
    grn.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(grn)

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_GRN,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=f"GRN {grn.id}",
        changes=", ".join(changes),
    )

    return _map_grn(grn)

from sqlalchemy import select
from sqlalchemy.orm import noload
from fastapi import HTTPException, status

async def verify_grn(
    db: AsyncSession,
    grn_id: int,
    current_user,
):
    # ----------------------------------
    # 1. Lock GRN row (NO JOINS)
    # ----------------------------------
    result = await db.execute(
        select(GRN)
        .options(noload("*"))
        .where(
            GRN.id == grn_id,
            GRN.is_deleted.is_(False),
        )
        .with_for_update()
    )
    grn = result.scalar_one_or_none()

    if not grn:
        raise HTTPException(404, "GRN not found")

    if grn.status != GRNStatus.DRAFT:
        raise HTTPException(409, "GRN already processed")

    # ----------------------------------
    # 2. EXPLICITLY load items (safe)
    # ----------------------------------
    items_result = await db.execute(
        select(GRNItem)
        .where(GRNItem.grn_id == grn.id)
    )
    items = items_result.scalars().all()

    if not items:
        raise HTTPException(400, "GRN has no items")

    # ----------------------------------
    # 3. Apply inventory movements
    # ----------------------------------
    for item in items:
        await apply_inventory_movement(
            db=db,
            product_id=item.product_id,
            location_id=1,
            quantity_change=item.quantity,
            movement_type=InventoryMovementType.STOCK_IN,
            reference_type="GRN",
            reference_id=grn.id,
            actor_user=current_user,
        )

    # ----------------------------------
    # 4. Mark verified
    # ----------------------------------
    grn.status = GRNStatus.VERIFIED
    grn.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(grn)

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.VERIFY_GRN,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=f"GRN {grn.id}",
    )

    return _map_grn(grn)

async def delete_grn(
    db: AsyncSession,
    grn_id: int,
    current_user,
):
    grn = await db.get(GRN, grn_id)
    if not grn or grn.is_deleted:
        raise HTTPException(404, "GRN not found")

    if grn.status == GRNStatus.VERIFIED:
        raise HTTPException(409, "Verified GRN cannot be deleted")

    grn.is_deleted = True
    grn.updated_by_id = current_user.id

    await db.commit()

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DELETE_GRN,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=f"GRN {grn.id}",
    )

    return _map_grn(grn)