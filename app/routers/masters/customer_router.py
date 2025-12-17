# app/routers/customer_router.py

from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.response import APIResponse
from app.schemas.masters.customer_schema import (
    CustomerCreate,
    CustomerUpdate,
    CustomerOut,
    CustomerListData,
)
from app.services.masters.customer_service import (
    create_customer,
    get_customer,
    list_customers,
    update_customer,
    deactivate_customer,
)
from app.utils.check_roles import require_role
from app.utils.response import success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/billing/customers", tags=["Customers"])
logger = get_logger(__name__)


@router.post("/", response_model=APIResponse[CustomerOut])
async def create_customer_api(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
):
    logger.info("Create customer", extra={"email": payload.email})
    customer = await create_customer(db, payload, user)
    return success_response("Customer created successfully", customer)


@router.get("/{customer_id}", response_model=APIResponse[CustomerOut])
async def get_customer_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),
):
    logger.info("Get customer", extra={"customer_id": customer_id})
    customer = await get_customer(db, customer_id)
    return success_response("Customer fetched successfully", customer)

@router.get("/", response_model=APIResponse[CustomerListData])
async def list_customers_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "sales", "cashier"])),

    name: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    logger.info(
        "List customers",
        extra={
            "customer_name": name,
            "customer_email": email,
            "customer_phone": phone,
            "page": page,
            "page_size": page_size,
        },
    )

    data = await list_customers(
        db=db,
        name=name,
        email=email,
        phone=phone,
        page=page,
        page_size=page_size,
    )

    return success_response("Customers fetched successfully", data)


@router.patch("/{customer_id}", response_model=APIResponse[CustomerOut])
async def update_customer_api(
    customer_id: int,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Update customer", extra={"customer_id": customer_id})
    customer = await update_customer(db, customer_id, payload, user)
    return success_response("Customer updated successfully", customer)


@router.delete("/{customer_id}", response_model=APIResponse[CustomerOut])
async def deactivate_customer_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Deactivate customer", extra={"customer_id": customer_id})
    customer = await deactivate_customer(db, customer_id, user)
    return success_response("Customer deactivated successfully", customer)
