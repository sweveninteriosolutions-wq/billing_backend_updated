# app/routers/customer_router.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.masters.customer_schema import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)
from app.services.masters.customer_service import (
    create_customer,
    get_customer,
    get_all_customers,
    update_customer,
    delete_customer,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/billing/customers", tags=["Customers"])


@router.post("/", response_model=CustomerResponse)
async def create_customer_api(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales", "cashier"])),
):
    return await create_customer(db, payload, current_user)


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales", "cashier"])),
):
    return await get_customer(db, customer_id)


@router.get("/", response_model=CustomerListResponse)
async def list_customers_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "sales", "cashier"])),
    name: str | None = Query(None),
    email: str | None = Query(None),
    phone: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    return await get_all_customers(
        db, name, email, phone, limit, offset, sort_by, order
    )


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer_api(
    customer_id: int,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await update_customer(db, customer_id, payload, current_user)


@router.delete("/{customer_id}", response_model=CustomerResponse)
async def delete_customer_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await delete_customer(db, customer_id, current_user)