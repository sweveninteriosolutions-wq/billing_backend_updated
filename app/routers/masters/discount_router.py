# app/routers/masters/discount_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.core.db import get_db
from app.schemas.masters.discount_schemas import (
    DiscountCreate,
    DiscountUpdate,
    DiscountListData,
    DiscountOut,
)
from app.services.masters.discount_service import (
    create_discount,
    list_discounts,
    get_discount,
    update_discount,
    deactivate_discount,
    reactivate_discount,
)
from app.utils.check_roles import require_role
from app.utils.response import APIResponse, success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/discounts", tags=["Discounts"])
logger = get_logger(__name__)


@router.post("/", response_model=APIResponse[DiscountOut])
async def create_discount_api(
    payload: DiscountCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Create discount", extra={"code": payload.code})
    data = await create_discount(db, payload, user)
    return success_response("Discount created successfully", data)


@router.get("/", response_model=APIResponse[DiscountListData])
async def list_discounts_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),

    code: str | None = Query(None),
    name: str | None = Query(None),
    discount_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    logger.info("List discounts")
    data = await list_discounts(
        db=db,
        code=code,
        name=name,
        discount_type=discount_type,
        is_active=is_active,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return success_response("Discounts fetched successfully", data)


@router.get("/{discount_id}", response_model=APIResponse[DiscountOut])
async def get_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Get discount", extra={"discount_id": discount_id})
    data = await get_discount(db, discount_id)
    return success_response("Discount fetched successfully", data)


@router.patch("/{discount_id}", response_model=APIResponse[DiscountOut])
async def update_discount_api(
    discount_id: int,
    payload: DiscountUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Update discount", extra={"discount_id": discount_id})
    data = await update_discount(db, discount_id, payload, user)
    return success_response("Discount updated successfully", data)


@router.patch("/{discount_id}/deactivate", response_model=APIResponse[DiscountOut])
async def deactivate_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Deactivate discount", extra={"discount_id": discount_id})
    data = await deactivate_discount(db, discount_id, user)
    return success_response("Discount deactivated successfully", data)


@router.patch("/{discount_id}/activate", response_model=APIResponse[DiscountOut])
async def reactivate_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    logger.info("Reactivate discount", extra={"discount_id": discount_id})
    data = await reactivate_discount(db, discount_id, user)
    return success_response("Discount reactivated successfully", data)
