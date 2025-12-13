# app/services/customer_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc
from sqlalchemy.orm import aliased
from fastapi import HTTPException, status

from app.models.masters.customer_models import Customer
from app.models.users.user_models import User
from app.schemas.masters.customer_schema import (
    CustomerCreate,
    CustomerUpdate,
    CustomerOut,
    CustomerResponse,
    CustomerListResponse,
)
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode

def _map_customer(customer: Customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        address=customer.address,
        is_active=customer.is_active,
        version=customer.version,

        created_by=customer.created_by_id,
        updated_by=customer.updated_by_id,

        created_by_name=customer.created_by_username,   # ✅ from hybrid_property
        updated_by_name=customer.updated_by_username,   # ✅ from hybrid_property

        created_at=customer.created_at,
    )


async def create_customer(
    db: AsyncSession,
    payload: CustomerCreate,
    current_user,
):
    # Pre-check: unique email
    exists = await db.scalar(
        select(Customer.id).where(Customer.email == payload.email)
    )
    if exists:
        raise HTTPException(status_code=400, detail="Customer already exists")

    customer = Customer(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        created_by_id=current_user.id,   # ✅ FIX
        updated_by_id=current_user.id,   # ✅ FIX
    )

    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_CUSTOMER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=customer.name,
    )

    return CustomerResponse(
        message="Customer created successfully",
        data=_map_customer(customer),
    )


async def get_customer(
    db: AsyncSession,
    customer_id: int,
) -> CustomerResponse:

    customer = await db.get(Customer, customer_id)
    if not customer or not customer.is_active:
        raise HTTPException(status_code=404, detail="Customer not found")

    return CustomerResponse(
        message="Customer retrieved successfully",
        data=_map_customer(customer),
    )

async def get_all_customers(
    db: AsyncSession,
    name: str | None,
    email: str | None,
    phone: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    order: str,
) -> CustomerListResponse:

    query = select(Customer).where(Customer.is_active == True)

    if name:
        query = query.where(Customer.name.ilike(f"%{name}%"))
    if email:
        query = query.where(Customer.email.ilike(f"%{email}%"))
    if phone:
        query = query.where(Customer.phone.ilike(f"%{phone}%"))

    sort_map = {
        "name": Customer.name,
        "created_at": Customer.created_at,
    }
    sort_col = sort_map.get(sort_by, Customer.created_at)
    query = query.order_by(asc(sort_col) if order == "asc" else desc(sort_col))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    result = await db.execute(query.offset(offset).limit(limit))
    customers = result.scalars().all()

    return CustomerListResponse(
        message="Customers retrieved successfully",
        total=total or 0,
        data=[_map_customer(c) for c in customers],
    )
async def update_customer(
    db: AsyncSession,
    customer_id: int,
    payload: CustomerUpdate,
    current_user,
):

    customer = await db.get(Customer, customer_id)
    if not customer or not customer.is_active:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Track previous values
    changes = []

    if payload.name and payload.name != customer.name:
        changes.append("name updated")

    if payload.email and payload.email != customer.email:
        changes.append("email updated")

    if payload.phone and payload.phone != customer.phone:
        changes.append("phone updated")

    if payload.address and payload.address != customer.address:
        changes.append("address updated")

    if payload.is_active is not None and payload.is_active != customer.is_active:
        changes.append(
            "activated" if payload.is_active else "deactivated"
        )

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No changes detected",
        )

    # Optimistic locking update
    stmt = (
        update(Customer)
        .where(
            Customer.id == customer_id,
            Customer.version == payload.version,
            Customer.is_active == True,
        )
        .values(
            **payload.dict(exclude_unset=True, exclude={"version"}),
            updated_by_id=current_user.id,
            version=Customer.version + 1,
        )
        .returning(Customer)
    )

    result = await db.execute(stmt)
    updated_customer = result.scalar_one_or_none()

    if not updated_customer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer was modified by another process",
        )

    await db.commit()

    # Activity log with detailed changes
    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_CUSTOMER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=updated_customer.name,
        changes=", ".join(changes),
    )

    return CustomerResponse(
        message="Customer updated successfully",
        data=_map_customer(updated_customer),
    )


async def delete_customer(
    db: AsyncSession,
    customer_id: int,
    current_user,
) -> CustomerResponse:

    customer = await db.get(Customer, customer_id)
    if not customer or not customer.is_active:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.is_active = False
    customer.updated_by_id  = current_user.id
    customer.version += 1

    await db.commit()

    await emit_activity(
        db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DEACTIVATE_CUSTOMER,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=customer.name,
    )

    return CustomerResponse(
        message="Customer deactivated successfully",
        data=_map_customer(customer),
    )


