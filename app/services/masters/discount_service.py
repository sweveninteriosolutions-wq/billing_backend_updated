# app/services/masters/discount_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from datetime import date

from app.models.masters.discount_models import Discount
from app.schemas.masters.discount_schemas import DiscountCreate, DiscountUpdate, DiscountOut, DiscountListData, VersionPayload
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
from sqlalchemy import select, and_

async def _assert_no_date_overlap(
    *,
    db: AsyncSession,
    code: str,
    start_date: date,
    end_date: date,
    exclude_id: int | None = None,
):
    query = select(Discount.id).where(
        Discount.code == code,
        Discount.is_deleted.is_(False),
        Discount.start_date <= end_date,
        Discount.end_date >= start_date,
    )

    if exclude_id:
        query = query.where(Discount.id != exclude_id)

    exists = await db.scalar(query)
    if exists:
        raise AppException(
            409,
            "Another discount with overlapping date range exists",
            ErrorCode.DISCOUNT_DATE_OVERLAP,
        )



# ---------------- VALIDATION ----------------
def _validate_discount(discount_type: str, value: Decimal):
    if discount_type == "percentage":
        if value <= 0 or value > 100:
            raise AppException(400, "Invalid percentage discount", ErrorCode.DISCOUNT_INVALID_VALUE)
    elif discount_type == "flat":
        if value <= 0:
            raise AppException(400, "Invalid flat discount", ErrorCode.DISCOUNT_INVALID_VALUE)


def _map_discount(discount: Discount) -> DiscountOut:
    return DiscountOut(
        id=discount.id,
        name=discount.name,
        code=discount.code,
        discount_type=discount.discount_type,
        discount_value=discount.discount_value,

        is_active=discount.is_active,
        is_deleted=discount.is_deleted,

        start_date=discount.start_date,
        end_date=discount.end_date,
        usage_limit=discount.usage_limit,
        used_count=discount.used_count,
        note=discount.note,

        created_at=discount.created_at,
        updated_at=discount.updated_at,

        created_by=discount.created_by_id,
        updated_by=discount.updated_by_id,

        created_by_name=(
            discount.created_by.username
            if getattr(discount, "created_by", None)
            else None
        ),
        updated_by_name=(
            discount.updated_by.username
            if getattr(discount, "updated_by", None)
            else None
        ),
    )



# ---------------- CREATE ----------------
async def create_discount(db: AsyncSession, payload: DiscountCreate, user):
    if payload.start_date >= payload.end_date:
        raise AppException(
            400,
            "Invalid date range",
            ErrorCode.DISCOUNT_INVALID_RANGE,
        )

    _validate_discount(payload.discount_type, payload.discount_value)

    await _assert_no_date_overlap(
        db=db,
        code=payload.code,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )

    try:
        discount = Discount(
            **payload.model_dump(),
            is_active=True,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(discount)
        await db.flush()
    except IntegrityError:
        raise AppException(
            409,
            "Discount code already exists",
            ErrorCode.DISCOUNT_CODE_EXISTS,
        )

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
    return _map_discount(discount)



# ---------------- GET ----------------
async def get_discount(db: AsyncSession, discount_id: int):
    discount = await db.get(Discount, discount_id)
    if not discount or discount.is_deleted:
        raise AppException(404, "Discount not found", ErrorCode.DISCOUNT_NOT_FOUND)
    return _map_discount(discount)


# ---------------- LIST ----------------
async def list_discounts(
    *,
    db,
    code,
    name,
    discount_type,
    is_active,
    is_deleted,
    start_date,
    end_date,
    page,
    page_size,
):
    query = select(Discount)

    if code:
        query = query.where(Discount.code.ilike(f"%{code}%"))
    if name:
        query = query.where(Discount.name.ilike(f"%{name}%"))
    if discount_type:
        query = query.where(Discount.discount_type == discount_type)
    if is_active is not None:
        query = query.where(Discount.is_active == is_active)
    if is_deleted is not None:
        query = query.where(Discount.is_deleted == is_deleted)
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

    return DiscountListData(
        total=total or 0,
        items=[_map_discount(d) for d in result.scalars().all()],
    )


# ---------------- UPDATE ----------------
async def update_discount(
    db: AsyncSession,
    discount_id: int,
    payload: DiscountUpdate,
    user,
):
    current = await db.get(Discount, discount_id)
    if not current or current.is_deleted:
        raise AppException(
            404,
            "Discount not found",
            ErrorCode.DISCOUNT_NOT_FOUND,
        )

    data = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not data:
        raise AppException(400, "No changes detected", ErrorCode.VALIDATION_ERROR)

    new_start = data.get("start_date", current.start_date)
    new_end = data.get("end_date", current.end_date)

    if new_start >= new_end:
        raise AppException(
            400,
            "Invalid date range",
            ErrorCode.DISCOUNT_INVALID_RANGE,
        )

    await _assert_no_date_overlap(
        db=db,
        code=current.code,
        start_date=new_start,
        end_date=new_end,
        exclude_id=current.id,
    )

    if "discount_type" in data or "discount_value" in data:
        _validate_discount(
            data.get("discount_type", current.discount_type),
            data.get("discount_value", current.discount_value),
        )

    stmt = (
        update(Discount)
        .where(
            Discount.id == discount_id,
            Discount.is_deleted.is_(False),
        )
        .values(
            **data,
            updated_by_id=user.id,
        )
        .returning(Discount)
    )

    result = await db.execute(stmt)
    discount = result.scalar_one_or_none()

    if not discount:
        raise AppException(
            409,
            "Discount was modified by another process",
            ErrorCode.DISCOUNT_VERSION_CONFLICT,
        )

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
    return _map_discount(discount)

# ---------------- DEACTIVATE ----------------
async def deactivate_discount(
    db: AsyncSession,
    discount_id: int,
    user,
):
    stmt = (
        update(Discount)
        .where(
            Discount.id == discount_id,
            Discount.is_deleted.is_(False),
        )
        .values(
            is_active=False,
            is_deleted=True,
            updated_by_id=user.id,
        )
        .returning(Discount)
    )

    result = await db.execute(stmt)
    discount = result.scalar_one_or_none()

    if not discount:
        raise AppException(
            409,
            "Discount was modified or already deleted",
            ErrorCode.DISCOUNT_VERSION_CONFLICT,
        )

    await emit_activity(
    db=db,
    user_id=user.id,
    username=user.username,
    code=ActivityCode.DEACTIVATE_DISCOUNT,
    actor_role=user.role.capitalize(),
    actor_email=user.username,
    target_name=discount.name,
    target_code=discount.code,
)


    await db.commit()
    return _map_discount(discount)

# ---------------- REACTIVATE ----------------
async def reactivate_discount(
    db: AsyncSession,
    discount_id: int,
    user,
):
    discount = await db.get(Discount, discount_id)

    if not discount:
        raise AppException(
            404,
            "Discount not found",
            ErrorCode.DISCOUNT_NOT_FOUND,
        )

    if not discount.is_deleted:
        raise AppException(
            400,
            "Discount is already active",
            ErrorCode.VALIDATION_ERROR,
        )

    if discount.end_date < date.today():
        raise AppException(
            400,
            "Cannot reactivate expired discount",
            ErrorCode.DISCOUNT_EXPIRED,
        )

    if (
        discount.usage_limit is not None
        and discount.used_count >= discount.usage_limit
    ):
        raise AppException(
            400,
            "Discount usage limit already reached",
            ErrorCode.DISCOUNT_USAGE_LIMIT_REACHED,
        )

    stmt = (
        update(Discount)
        .where(
            Discount.id == discount_id,
            Discount.is_deleted.is_(True),
        )
        .values(
            is_deleted=False,
            is_active=True,
            version=Discount.version + 1,
            updated_by_id=user.id,
        )
        .returning(Discount)
    )

    result = await db.execute(stmt)
    discount = result.scalar_one_or_none()

    if not discount:
        raise AppException(
            409,
            "Discount was modified by another process",
            ErrorCode.DISCOUNT_VERSION_CONFLICT,
        )

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
    return _map_discount(discount)
