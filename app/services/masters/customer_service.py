# app/services/masters/customer_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc, text

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
from typing import Optional
from sqlalchemy.exc import IntegrityError
import uuid
import re

logger = get_logger(__name__)


def generate_customer_code(name: str, phone: Optional[str]) -> str:
    clean_name = re.sub(r"[^A-Za-z]", "", name or "").upper()
    prefix_name = clean_name[:3].ljust(3, "X")
    digits = re.sub(r"[^0-9]", "", phone or "")
    prefix_phone = digits[-3:] if len(digits) >= 3 else digits.zfill(3)
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"CUST-{prefix_name}{prefix_phone}-{unique_part}"


def _map_customer(customer: Customer) -> CustomerOut:
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

        created_by_name=(
            customer.created_by.username
            if getattr(customer, "created_by", None)
            else None
        ),
        updated_by_name=(
            customer.updated_by.username
            if getattr(customer, "updated_by", None)
            else None
        ),

        created_at=customer.created_at,
    )


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

    # Try once (UUID collision is astronomically unlikely)
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
        # Only possible cause here is unique constraint violation
        raise AppException(
            409,
            "Customer code already exists. Please retry.",
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
    await db.refresh(customer)

    return _map_customer(customer)


# =========================
# GET
# =========================
async def get_customer(db: AsyncSession, customer_id: int):
    customer = await db.get(Customer, customer_id)
    if not customer or not customer.is_active:
        raise AppException(
            404,
            "Customer not found",
            ErrorCode.CUSTOMER_NOT_FOUND,
        )

    return _map_customer(customer)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

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
    params = {
        "limit": page_size,
        "offset": offset,
    }

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
    select
        c.id,
        c.customer_code,
        c.name,
        c.email,
        c.phone,
        c.address,
        c.gstin,
        c.is_active,
        c.is_deleted,
        c.version,
        c.created_at,
        c.updated_at,

        c.created_by_id,
        cu.username AS created_by_name,

        c.updated_by_id,
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

    return {
        "total": total,
        "items": items,
    }



# =========================
# UPDATE (OPTIMISTIC)
# =========================
async def update_customer(
    db: AsyncSession,
    customer_id: int,
    payload: CustomerUpdate,
    user,
):
    # ---------------------------------
    # FETCH CURRENT STATE (FOR AUDIT)
    # ---------------------------------
    current = await db.get(Customer, customer_id)
    if not current or not current.is_active:
        raise AppException(
            404,
            "Customer not found",
            ErrorCode.CUSTOMER_NOT_FOUND,
        )

    changes: list[str] = []

    if payload.name is not None and payload.name != current.name:
        changes.append(f"name: '{current.name}' → '{payload.name}'")

    if payload.email is not None and payload.email != current.email:
        changes.append(f"email: '{current.email}' → '{payload.email}'")

    if payload.gstin is not None and payload.gstin != current.gstin:
        changes.append(f"gstin: '{current.gstin}' → '{payload.gstin}'")

    if payload.phone is not None and payload.phone != current.phone:
        old_phone = current.phone[-4:] if current.phone else "None"
        new_phone = payload.phone[-4:]
        changes.append(f"phone: ****{old_phone} → ****{new_phone}")

    if payload.address is not None:
        old_address = current.address or {}
        new_address = payload.address

        changed_fields = [
            key
            for key in new_address
            if new_address.get(key) != old_address.get(key)
        ]

        if changed_fields:
            changes.append(
                f"address fields updated: {', '.join(changed_fields)}"
            )


    if payload.is_active is not None and payload.is_active != current.is_active:
        changes.append(
            "activated" if payload.is_active else "deactivated"
        )

    if not changes:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    # ---------------------------------
    # OPTIMISTIC UPDATE
    # ---------------------------------
    stmt = (
        update(Customer)
        .where(
            Customer.id == customer_id,
            Customer.version == payload.version,
            Customer.is_active.is_(True),
        )
        .values(
            **payload.dict(exclude_unset=True, exclude={"version"}),
            updated_by_id=user.id,
            version=Customer.version + 1,
        )
        .returning(Customer)
    )

    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    if not customer:
        raise AppException(
            409,
            "Customer was modified by another process",
            ErrorCode.CUSTOMER_VERSION_CONFLICT,
        )

    # ---------------------------------
    # ACTIVITY LOG (REQUIRED CONTEXT)
    # ---------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_CUSTOMER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=customer.name,
        changes=", ".join(changes),
    )

    await db.commit()
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
    return _map_customer(customer)
