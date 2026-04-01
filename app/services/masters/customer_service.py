# app/services/masters/customer_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from sqlalchemy.orm import selectinload
from typing import Optional
from sqlalchemy.exc import IntegrityError

from app.models.masters.customer_models import Customer
from app.schemas.masters.customer_schema import (
    CustomerCreate,
    CustomerUpdate,
    CustomerOut,
    CustomerListData,
)

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode
from app.utils.logger import get_logger

import uuid
import re

logger = get_logger(__name__)


# ------------------------
# HELPERS
# ------------------------
def generate_customer_code(name: str, phone: Optional[str]) -> str:
    clean_name = re.sub(r"[^A-Za-z]", "", name or "").upper()
    prefix_name = clean_name[:3].ljust(3, "X")

    digits = re.sub(r"[^0-9]", "", phone or "")
    prefix_phone = digits[-3:] if len(digits) >= 3 else digits.zfill(3)

    unique_part = uuid.uuid4().hex[:6].upper()
    return f"CUST-{prefix_name}{prefix_phone}-{unique_part}"


def _map_customer(customer: Customer) -> CustomerOut:
    created_by = customer.__dict__.get("created_by")
    updated_by = customer.__dict__.get("updated_by")

    return CustomerOut(
        id=customer.id,
        customer_code=customer.customer_code,
        name=customer.name,
        email=customer.email,
        gstin=customer.gstin,
        phone=customer.phone,
        address=customer.address,
        is_active=customer.is_active,
        version=customer.version,
        created_by=customer.created_by_id,
        updated_by=customer.updated_by_id,
        created_by_name=created_by.username if created_by else None,
        updated_by_name=updated_by.username if updated_by else None,
        created_at=customer.created_at,
    )


async def _get_customer_with_relations(db: AsyncSession, customer_id: int):
    stmt = (
        select(Customer)
        .options(
            selectinload(Customer.created_by),
            selectinload(Customer.updated_by),
        )
        .where(Customer.id == customer_id)
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# =========================
# CREATE
# =========================
async def create_customer(db: AsyncSession, payload: CustomerCreate, user):
    exists = await db.scalar(
        select(Customer.id).where(Customer.email == payload.email)
    )

    if exists:
        raise AppException(
            400,
            "Customer already exists",
            ErrorCode.CUSTOMER_EMAIL_EXISTS,
        )

    customer_code = generate_customer_code(payload.name, payload.phone)

    customer = Customer(
        customer_code=customer_code,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(customer)

    try:
        await db.flush()
    except IntegrityError:
        raise AppException(
            409,
            "Customer code already exists",
            ErrorCode.CUSTOMER_CODE_EXISTS,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_CUSTOMER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=customer.name,
    )

    await db.commit()

    # ✅ REFETCH WITH RELATIONS
    customer = await _get_customer_with_relations(db, customer.id)

    return _map_customer(customer)


# =========================
# GET
# =========================
async def get_customer(db: AsyncSession, customer_id: int):
    customer = await _get_customer_with_relations(db, customer_id)

    if not customer or not customer.is_active:
        raise AppException(
            404,
            "Customer not found",
            ErrorCode.CUSTOMER_NOT_FOUND,
        )

    return _map_customer(customer)


# =========================
# LIST
# =========================
async def list_customers(
    *,
    db: AsyncSession,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    is_active: Optional[bool],
    page: int,
    page_size: int,
):
    offset = (page - 1) * page_size

    conditions = []
    params = {"limit": page_size, "offset": offset}

    if name:
        conditions.append("c.name ILIKE :name")
        params["name"] = f"%{name}%"

    if email:
        conditions.append("c.email ILIKE :email")
        params["email"] = f"%{email}%"

    if phone:
        conditions.append("c.phone ILIKE :phone")
        params["phone"] = f"%{phone}%"

    if is_active is not None:
        conditions.append("c.is_active = :is_active")
        params["is_active"] = is_active

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    sql = f"""
    SELECT
        c.*,
        cu.username AS created_by_name,
        uu.username AS updated_by_name,
        COUNT(*) OVER() AS total
    FROM customers c
    LEFT JOIN users cu ON cu.id = c.created_by_id
    LEFT JOIN users uu ON uu.id = c.updated_by_id
    {where_clause}
    ORDER BY c.created_at DESC
    LIMIT :limit OFFSET :offset
    """

    result = await db.execute(text(sql), params)
    rows = result.mappings().all()

    total = rows[0]["total"] if rows else 0

    items = []
    for r in rows:
        item = dict(r)
        item.pop("total", None)
        items.append(item)

    return CustomerListData(total=total, items=items)


# =========================
# UPDATE
# =========================
async def update_customer(
    db: AsyncSession,
    customer_id: int,
    payload: CustomerUpdate,
    user,
):
    current = await db.get(Customer, customer_id)

    if not current or not current.is_active:
        raise AppException(
            404,
            "Customer not found",
            ErrorCode.CUSTOMER_NOT_FOUND,
        )

    data = payload.model_dump(exclude_unset=True, exclude={"version"})

    if not data:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    stmt = (
        update(Customer)
        .where(
            Customer.id == customer_id,
            Customer.version == payload.version,
            Customer.is_active.is_(True),
        )
        .values(
            **data,
            updated_by_id=user.id,
            version=Customer.version + 1,
        )
    )

    result = await db.execute(stmt)

    if result.rowcount == 0:
        raise AppException(
            409,
            "Customer was modified by another process",
            ErrorCode.CUSTOMER_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_CUSTOMER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=current.name,
    )

    await db.commit()

    # ✅ REFETCH
    customer = await _get_customer_with_relations(db, customer_id)

    return _map_customer(customer)


# =========================
# DEACTIVATE
# =========================
async def deactivate_customer(db: AsyncSession, customer_id: int, user):
    customer = await db.get(Customer, customer_id)

    if not customer or not customer.is_active:
        raise AppException(
            404,
            "Customer not found",
            ErrorCode.CUSTOMER_NOT_FOUND,
        )

    customer.is_active = False
    customer.updated_by_id = user.id
    customer.version += 1

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DEACTIVATE_CUSTOMER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=customer.name,
    )

    await db.commit()

    customer = await _get_customer_with_relations(db, customer_id)

    return _map_customer(customer)