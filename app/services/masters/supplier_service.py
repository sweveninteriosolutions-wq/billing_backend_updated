from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc, text
from sqlalchemy.exc import IntegrityError
import uuid
import re
from typing import Optional

from app.models.masters.supplier_models import Supplier
from app.schemas.masters.supplier_schemas import (
    SupplierCreate,
    SupplierUpdate,
    SupplierOut,
    SupplierListData,
)
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
from app.utils.logger import get_logger

logger = get_logger(__name__)


# =========================
# CODE GENERATOR
# =========================
def generate_supplier_code(name: str, phone: Optional[str]) -> str:
    clean_name = re.sub(r"[^A-Za-z]", "", name or "").upper()
    prefix_name = clean_name[:3].ljust(3, "X")
    digits = re.sub(r"[^0-9]", "", phone or "")
    prefix_phone = digits[-3:] if len(digits) >= 3 else digits.zfill(3)
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"SUP-{prefix_name}{prefix_phone}-{unique_part}"


# =========================
# MAPPER
# =========================
def _map_supplier(supplier: Supplier) -> SupplierOut:
    return SupplierOut(
        id=supplier.id,
        supplier_code=supplier.supplier_code,
        name=supplier.name,
        contact_person=supplier.contact_person,
        phone=supplier.phone,
        email=supplier.email,
        address=supplier.address,

        is_deleted=supplier.is_deleted,
        version=supplier.version,

        created_by=supplier.created_by_id,
        updated_by=supplier.updated_by_id,
        created_by_name=(
            supplier.created_by.username
            if getattr(supplier, "created_by", None)
            else None
        ),
        updated_by_name=(
            supplier.updated_by.username
            if getattr(supplier, "updated_by", None)
            else None
        ),

        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


# =========================
# CREATE
# =========================
async def create_supplier(
    db: AsyncSession,
    payload: SupplierCreate,
    user,
):
    # ------------------------------------
    # Fast pre-check (UX optimization)
    # ------------------------------------
    exists = await db.scalar(
        select(Supplier.id).where(
            Supplier.name == payload.name,
            Supplier.is_deleted.is_(False),
        )
    )
    if exists:
        raise AppException(
            409,
            "Supplier already exists",
            ErrorCode.SUPPLIER_NAME_EXISTS,
        )

    supplier = Supplier(
        supplier_code=generate_supplier_code(payload.name, payload.phone),
        **payload.model_dump(),
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(supplier)

    try:
        await db.flush()  # forces INSERT, catches constraint issues early
    except IntegrityError:
        await db.rollback()
        raise AppException(
            409,
            "Supplier already exists",
            ErrorCode.SUPPLIER_NAME_EXISTS,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_SUPPLIER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=supplier.name,
    )

    await db.commit()
    await db.refresh(supplier)

    return _map_supplier(supplier)


# =========================
# GET
# =========================
async def get_supplier(db: AsyncSession, supplier_id: int):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier or supplier.is_deleted:
        raise AppException(
            404,
            "Supplier not found",
            ErrorCode.SUPPLIER_NOT_FOUND,
        )

    return _map_supplier(supplier)

async def list_suppliers(
    *,
    db: AsyncSession,
    search: Optional[str],
    is_deleted: Optional[bool],
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
):
    sort_map = {
        "name": "s.name",
        "created_at": "s.created_at",
        "email": "s.email",
        "phone": "s.phone",
    }

    sort_col = sort_map.get(sort_by)
    if not sort_col:
        raise AppException(400, "Invalid sort field", ErrorCode.VALIDATION_ERROR)

    sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    offset = (page - 1) * page_size

    conditions: list[str] = []
    params = {
        "limit": page_size,
        "offset": offset,
    }

    # 🔍 Search filter
    if search:
        conditions.append(
            "(s.name ILIKE :search OR s.email ILIKE :search OR s.phone ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    # 🗑️ is_deleted filter
    if is_deleted is not None:
        conditions.append("s.is_deleted = :is_deleted")
        params["is_deleted"] = is_deleted

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = f"WHERE {where_clause}"

    sql = f"""
        SELECT
            s.id,
            s.supplier_code,
            s.name,
            s.contact_person,
            s.email,
            s.phone,
            s.gstin,
            s.version,
            s.is_deleted,
            s.created_at,
            s.updated_at,

            s.created_by_id AS created_by,
            s.updated_by_id AS updated_by,
            cu.username AS created_by_name,
            uu.username AS updated_by_name,

            COUNT(*) OVER() AS total
        FROM suppliers s
        LEFT JOIN users cu ON cu.id = s.created_by_id
        LEFT JOIN users uu ON uu.id = s.updated_by_id
        {where_clause}
        ORDER BY {sort_col} {sort_dir}
        LIMIT :limit OFFSET :offset
    """

    raw_rows = (await db.execute(text(sql), params)).mappings().all()

    total = raw_rows[0]["total"] if raw_rows else 0

    items = [
        {k: v for k, v in r.items() if k != "total"}
        for r in raw_rows
    ]

    return {
        "total": total,
        "items": items,
    }



# =========================
# UPDATE
# =========================
async def update_supplier(
    db: AsyncSession,
    supplier_id: int,
    payload: SupplierUpdate,
    user,
):
    current = await db.get(Supplier, supplier_id)
    if not current or current.is_deleted:
        raise AppException(
            404,
            "Supplier not found",
            ErrorCode.SUPPLIER_NOT_FOUND,
        )

    changes: list[str] = []

    # ---------------------------
    # DUPLICATE NAME CHECK (RESTORED)
    # ---------------------------
    if payload.name and payload.name != current.name:
        exists = await db.scalar(
            select(Supplier.id).where(
                Supplier.name == payload.name,
                Supplier.id != supplier_id,
                Supplier.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(
                409,
                "Supplier name already exists",
                ErrorCode.SUPPLIER_NAME_EXISTS,
            )

        changes.append(f"name: '{current.name}' → '{payload.name}'")

    if payload.contact_person and payload.contact_person != current.contact_person:
        changes.append(
            f"contact_person: '{current.contact_person}' → '{payload.contact_person}'"
        )

    if payload.phone and payload.phone != current.phone:
        changes.append(f"phone: '{current.phone}' → '{payload.phone}'")

    if payload.email and payload.email != current.email:
        changes.append(f"email: '{current.email}' → '{payload.email}'")

    if payload.address and payload.address != current.address:
        changes.append(f"address: '{current.address}' → '{payload.address}'")

    if not changes:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    stmt = (
        update(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.version == payload.version,
            Supplier.is_deleted.is_(False),
        )
        .values(
            **payload.model_dump(exclude_unset=True, exclude={"version"}),
            version=Supplier.version + 1,
            updated_by_id=user.id,
        )
        .returning(Supplier)
    )

    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise AppException(
            409,
            "Supplier was modified by another process",
            ErrorCode.SUPPLIER_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_SUPPLIER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=supplier.name,
        changes=", ".join(changes),
    )

    await db.commit()
    return _map_supplier(supplier)



# =========================
# DEACTIVATE
# =========================
async def deactivate_supplier(
    *,
    db: AsyncSession,
    supplier_id: int,
    version: int,
    user,
):
    stmt = (
        update(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.version == version,
            Supplier.is_deleted.is_(False),
        )
        .values(
            is_deleted=True,
            version=Supplier.version + 1,
            updated_by_id=user.id,
        )
        .returning(Supplier)
    )

    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()

    if not supplier:
        raise AppException(
            409,
            "Supplier was modified by another process or already deactivated",
            ErrorCode.SUPPLIER_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DEACTIVATE_SUPPLIER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=supplier.name,
    )

    await db.commit()
    return _map_supplier(supplier)
