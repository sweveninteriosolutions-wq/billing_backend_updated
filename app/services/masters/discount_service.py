from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException

from app.models.masters.discount_models import Discount
from app.schemas.masters.discount_schemas import (
    DiscountCreate,
    DiscountUpdate,
    DiscountOut,
    DiscountResponse,
    DiscountListResponse,
)
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode


# ---------------- VALIDATION ----------------
def validate_discount_logic(discount_type: str, discount_value: Decimal):
    if discount_type == "percentage":
        if not (Decimal("0") < discount_value <= Decimal("100")):
            raise HTTPException(400, "Percentage discount must be between 0 and 100")
    elif discount_type == "flat":
        if discount_value <= 0:
            raise HTTPException(400, "Flat discount must be greater than 0")
    else:
        raise HTTPException(400, "Invalid discount type")


# ---------------- MAPPER ----------------
def _map_discount(discount: Discount) -> DiscountOut:
    return DiscountOut.model_validate(discount)


# ---------------- CREATE ----------------
async def create_discount(db: AsyncSession, payload: DiscountCreate, user):
    if payload.start_date >= payload.end_date:
        raise HTTPException(400, "Start date must be before end date")

    validate_discount_logic(payload.discount_type, payload.discount_value)

    exists = await db.scalar(
        select(Discount.id).where(
            Discount.code == payload.code,
            Discount.is_deleted.is_(False),
        )
    )
    if exists:
        raise HTTPException(400, "Discount code already exists")

    discount = Discount(
        **payload.model_dump(),
        is_active=True,
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(discount)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=discount.name,
        target_code=discount.code,
    )

    await db.commit()
    await db.refresh(discount)

    return DiscountResponse(
        message="Discount created successfully",
        data=_map_discount(discount),
    )


# ---------------- GET ----------------
async def get_discount(db: AsyncSession, discount_id: int):
    discount = await db.get(Discount, discount_id)
    if not discount or discount.is_deleted:
        raise HTTPException(404, "Discount not found")

    return DiscountResponse(
        message="Discount retrieved successfully",
        data=_map_discount(discount),
    )


# ---------------- LIST ----------------
async def list_discounts(
    db: AsyncSession,
    *,
    code,
    name,
    discount_type,
    is_active,
    start_date,
    end_date,
    page,
    page_size,
):
    query = select(Discount).where(Discount.is_deleted.is_(False))

    if code:
        query = query.where(Discount.code.ilike(f"%{code}%"))
    if name:
        query = query.where(Discount.name.ilike(f"%{name}%"))
    if discount_type:
        query = query.where(Discount.discount_type == discount_type)
    if is_active is not None:
        query = query.where(Discount.is_active == is_active)
    if start_date:
        query = query.where(Discount.start_date >= start_date)
    if end_date:
        query = query.where(Discount.end_date <= end_date)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    result = await db.execute(
        query.order_by(Discount.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    discounts = result.scalars().all()

    return DiscountListResponse(
        message="Discounts retrieved successfully",
        total=total or 0,
        data=[_map_discount(d) for d in discounts],
    )


# ---------------- UPDATE ----------------
async def update_discount(db: AsyncSession, discount_id: int, payload: DiscountUpdate, user):
    discount = await db.get(Discount, discount_id)
    if not discount or discount.is_deleted:
        raise HTTPException(404, "Discount not found")

    data = payload.model_dump(exclude_unset=True)

    if "start_date" in data or "end_date" in data:
        if data.get("start_date", discount.start_date) >= data.get("end_date", discount.end_date):
            raise HTTPException(400, "Start date must be before end date")

    if "discount_type" in data or "discount_value" in data:
        validate_discount_logic(
            data.get("discount_type", discount.discount_type),
            data.get("discount_value", discount.discount_value),
        )

    for k, v in data.items():
        setattr(discount, k, v)

    discount.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=discount.name,
        target_code=discount.code,
        changes=", ".join(data.keys()),
    )

    await db.commit()
    await db.refresh(discount)

    return DiscountResponse(
        message="Discount updated successfully",
        data=_map_discount(discount),
    )


# ---------------- DEACTIVATE ----------------
async def deactivate_discount(
    db: AsyncSession,
    discount_id: int,
    current_user,
) -> DiscountResponse:

    discount = await db.get(Discount, discount_id)
    if not discount or discount.is_deleted:
        raise HTTPException(404, "Discount not found")

    discount.is_deleted = True
    discount.updated_by_id = current_user.id

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DEACTIVATE_DISCOUNT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=discount.name,
        target_code=discount.code,
    )

    await db.commit()
    await db.refresh(discount)

    return DiscountResponse(
        message="Discount deleted successfully",
        data=_map_discount(discount),
    )



# ---------------- REACTIVATE ----------------
async def reactivate_discount(db: AsyncSession, discount_id: int, user):
    discount = await db.get(Discount, discount_id)
    if not discount:
        raise HTTPException(404, "Discount not found")

    if not discount.is_deleted:
        raise HTTPException(400, "Discount already active")

    if discount.end_date < date.today():
        raise HTTPException(400, "Cannot reactivate expired discount")

    if discount.usage_limit is not None and discount.used_count >= discount.usage_limit:
        raise HTTPException(400, "Usage limit reached")

    discount.is_deleted = False
    discount.is_active = True
    discount.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.REACTIVATE_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=discount.name,
        target_code=discount.code,
    )

    await db.commit()
    await db.refresh(discount)

    return DiscountResponse(
        message="Discount reactivated successfully",
        data=_map_discount(discount),
    )
