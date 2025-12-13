from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from fastapi import HTTPException, status

from app.models.masters.supplier_models import Supplier
from app.schemas.masters.supplier_schemas import (
    SupplierCreateSchema,
    SupplierUpdateSchema,
    SupplierTableSchema,
)
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
from sqlalchemy import asc, desc

ALLOWED_SORT_FIELDS = {
    "name": Supplier.name,
    "created_at": Supplier.created_at,
    "email": Supplier.email,
    "phone": Supplier.phone,
}


# ======================================================
# INTERNAL MAPPER
# ======================================================
def _map_supplier(supplier: Supplier) -> SupplierTableSchema:
    return SupplierTableSchema(
        id=supplier.id,
        name=supplier.name,
        contact_person=supplier.contact_person,
        phone=supplier.phone,
        email=supplier.email,
        address=supplier.address,

        is_active=not supplier.is_deleted,
        version=supplier.version,

        created_at=supplier.created_at,
        updated_at=supplier.updated_at,

        created_by_id=supplier.created_by_id,
        updated_by_id=supplier.updated_by_id,
        created_by_name=(
            supplier.created_by.username if supplier.created_by else None
        ),
        updated_by_name=(
            supplier.updated_by.username if supplier.updated_by else None
        ),
    )


# ======================================================
# CREATE SUPPLIER
# ======================================================
async def create_supplier(
    db: AsyncSession,
    payload: SupplierCreateSchema,
    current_user,
):
    # Duplicate active supplier check
    exists = await db.scalar(
        select(Supplier.id).where(
            Supplier.name == payload.name,
            Supplier.is_deleted.is_(False),
        )
    )
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier with this name already exists",
        )

    supplier = Supplier(
        **payload.model_dump(),
        created_by_id=current_user.id,
    )

    db.add(supplier)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid supplier data",
        )

    await db.refresh(supplier)

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_SUPPLIER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=supplier.name,
    )

    return _map_supplier(supplier)



# ======================================================
# LIST SUPPLIERS
# ======================================================
async def list_suppliers(
    db: AsyncSession,
    search: str | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
):
    base = select(Supplier).where(Supplier.is_deleted.is_(False))

    if search:
        base = base.where(Supplier.name.ilike(f"%{search}%"))

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Supplier.created_at)
    sort_order = asc(sort_column) if order.lower() == "asc" else desc(sort_column)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(
        base.order_by(sort_order)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return total, [_map_supplier(s) for s in result.scalars().all()]


# ======================================================
# GET SUPPLIER
# ======================================================
async def get_supplier(db: AsyncSession, supplier_id: int):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")

    return _map_supplier(supplier)


# ======================================================
# UPDATE SUPPLIER (OPTIMISTIC LOCKING + DIFF LOGGING)
# ======================================================
async def update_supplier(
    db: AsyncSession,
    supplier_id: int,
    payload: SupplierUpdateSchema,
    current_user,
):
    existing = await db.get(Supplier, supplier_id)
    if not existing or existing.is_deleted:
        raise HTTPException(status_code=404, detail="Supplier not found")

    updates = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No changes provided",
        )

    # Duplicate name check (only if name is changing)
    if "name" in updates and updates["name"] != existing.name:
        dup = await db.scalar(
            select(Supplier.id).where(
                Supplier.name == updates["name"],
                Supplier.id != supplier_id,
                Supplier.is_deleted.is_(False),
            )
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Supplier name already exists",
            )

    # Calculate diff for activity log
    changes: list[str] = []
    for field, new_value in updates.items():
        old_value = getattr(existing, field)
        if old_value != new_value:
            changes.append(f"{field}: {old_value} → {new_value}")

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No actual changes detected",
        )

    stmt = (
        update(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.version == payload.version,
            Supplier.is_deleted.is_(False),
        )
        .values(
            **updates,
            version=Supplier.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(Supplier)
    )

    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier was modified by another process. Refresh and retry.",
        )

    await db.commit()

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_SUPPLIER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=supplier.name,
        changes=", ".join(changes),
    )

    return _map_supplier(supplier)



# ======================================================
# DEACTIVATE SUPPLIER (SOFT DELETE)
# ======================================================
async def deactivate_supplier(
    db: AsyncSession,
    supplier_id: int,
    payload: SupplierUpdateSchema,
    current_user,
):
    stmt = (
        update(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.version == payload.version,
            Supplier.is_deleted.is_(False),
        )
        .values(
            is_deleted=True,
            updated_by_id=current_user.id,
            version=Supplier.version + 1,
        )
        .returning(Supplier)
    )

    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier was modified by another process",
        )

    await db.commit()

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DEACTIVATE_SUPPLIER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=supplier.name,
    )

    return _map_supplier(supplier)




# ======================================================
# REACTIVATE SUPPLIER
# ======================================================
async def reactivate_supplier(
    db: AsyncSession,
    supplier_id: int,
    payload: SupplierUpdateSchema,
    current_user,
):
    stmt = (
        update(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.version == payload.version,
            Supplier.is_deleted.is_(True),
        )
        .values(
            is_deleted=False,
            updated_by_id=current_user.id,
            version=Supplier.version + 1,
        )
        .returning(Supplier)
    )

    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier was modified by another process",
        )

    await db.commit()

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.REACTIVATE_SUPPLIER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=supplier.name,
    )

    return _map_supplier(supplier)
