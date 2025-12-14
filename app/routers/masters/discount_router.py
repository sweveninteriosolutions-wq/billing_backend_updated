from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from app.core.db import get_db
from app.schemas.masters.discount_schemas import (
    DiscountCreate,
    DiscountUpdate,
    DiscountResponse,
    DiscountListResponse,
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

router = APIRouter(prefix="/discounts", tags=["Discounts"])


@router.post("/", response_model=DiscountResponse)
async def create_discount_api(
    payload: DiscountCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await create_discount(db, payload, current_user)


@router.get("/", response_model=DiscountListResponse)
async def list_discounts_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),

    code: str | None = Query(None),
    name: str | None = Query(None),
    discount_type: str | None = Query(None),
    is_active: bool | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await list_discounts(
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


@router.get("/{discount_id}", response_model=DiscountResponse)
async def get_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await get_discount(db, discount_id)


@router.patch("/{discount_id}", response_model=DiscountResponse)
async def update_discount_api(
    discount_id: int,
    payload: DiscountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await update_discount(db, discount_id, payload, current_user)


@router.delete("/{discount_id}", response_model=DiscountResponse)
async def deactivate_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await deactivate_discount(db, discount_id, current_user)


@router.post("/{discount_id}/activate", response_model=DiscountResponse)
async def reactivate_discount_api(
    discount_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    return await reactivate_discount(db, discount_id, current_user)
