# app/services/auth/activity_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc

from app.models.support.activity_models import UserActivity
from app.schemas.auth.activity_schemas import (
    UserActivityOut,
    UserActivityFilters,
)
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_SORT_FIELDS = {
    "created_at": UserActivity.created_at,
    "username": UserActivity.username_snapshot,
}


async def list_user_activities(
    *,
    db: AsyncSession,
    filters: UserActivityFilters,
):
    # -------------------------
    # Base queries
    # -------------------------
    query = select(UserActivity)
    count_query = select(func.count(UserActivity.id))

    # -------------------------
    # Filters
    # -------------------------
    if filters.user_id:
        query = query.where(UserActivity.user_id == filters.user_id)
        count_query = count_query.where(UserActivity.user_id == filters.user_id)

    if filters.username:
        query = query.where(
            UserActivity.username_snapshot.ilike(f"%{filters.username}%")
        )
        count_query = count_query.where(
            UserActivity.username_snapshot.ilike(f"%{filters.username}%")
        )

    # -------------------------
    # Sorting (safe)
    # -------------------------
    sort_column = ALLOWED_SORT_FIELDS.get(filters.sort_by)
    if not sort_column:
        raise AppException(
            400,
            "Invalid sort field",
            ErrorCode.VALIDATION_ERROR,
        )

    order_fn = desc if filters.sort_order == "desc" else asc
    query = query.order_by(order_fn(sort_column))

    # -------------------------
    # Pagination
    # -------------------------
    offset = (filters.page - 1) * filters.page_size
    query = query.limit(filters.page_size).offset(offset)

    # -------------------------
    # Execute
    # -------------------------
    total = await db.scalar(count_query)
    result = await db.execute(query)

    activities = result.scalars().all()

    logger.info(
        "User activities fetched",
        extra={
            "total": total,
            "page": filters.page,
            "page_size": filters.page_size,
        },
    )

    return {
        "total": total or 0,
        "items": [UserActivityOut.from_orm(a) for a in activities],
    }
