from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc
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
    return f"CUST-{prefix_name}{prefix_phone}-{unique_part}"


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
        is_active=not supplier.is_deleted,
        version=supplier.version,

        created_by=supplier.created_by_id,
        updated_by=supplier.updated_by_id,
        created_by_name=(
            supplier.created_by.username if supplier.created_by else None
        ),
        updated_by_name=(
            supplier.updated_by.username if supplier.updated_by else None
        ),
        created_at=supplier.created_at,
    )


# =========================
# CREATE
# =========================
async def create_supplier(db: AsyncSession, payload: SupplierCreate, user):
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
    await db.flush()

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


# =========================
# LIST (LATEST FIRST)
# =========================
async def list_suppliers(
    *,
    db: AsyncSession,
    search: Optional[str],
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
):
    query = select(Supplier).where(Supplier.is_deleted.is_(False))

    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%"))

    sort_map = {
        "name": Supplier.name,
        "created_at": Supplier.created_at,
        "email": Supplier.email,
        "phone": Supplier.phone,
    }

    sort_col = sort_map.get(sort_by)
    if not sort_col:
        raise AppException(
            400,
            "Invalid sort field",
            ErrorCode.VALIDATION_ERROR,
        )

    query = query.order_by(
        desc(sort_col) if sort_order == "desc" else asc(sort_col)
    )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    )

    result = await db.execute(
        query.offset(offset).limit(limit)
    )

    return SupplierListData(
        total=total or 0,
        items=[_map_supplier(s) for s in result.scalars().all()],
    )


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

    if payload.name and payload.name != current.name:
        changes.append(f"name: '{current.name}' → '{payload.name}'")

    if payload.contact_person and payload.contact_person != current.contact_person:
        changes.append(
            f"contact_person: '{current.contact_person}' → '{payload.contact_person}'"
        )

    if payload.phone and payload.phone != current.phone:
        changes.append("phone updated")

    if payload.email and payload.email != current.email:
        changes.append("email updated")

    if payload.address and payload.address != current.address:
        changes.append("address updated")

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
    db: AsyncSession,
    supplier_id: int,
    payload: SupplierUpdate,
    user,
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
        code=ActivityCode.DEACTIVATE_SUPPLIER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=supplier.name,
    )

    await db.commit()
    return _map_supplier(supplier)
