from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, asc
from typing import Optional

from app.models.support.activity_models import UserActivity


ALLOWED_SORT_FIELDS = {
    "created_at": UserActivity.created_at,
    "username": UserActivity.username_snapshot,
}


async def get_user_activities(
    *,
    db: AsyncSession,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    order: str = "desc",
):
    """
    Fetch paginated user activity logs with filters.
    """

    # -------------------------
    # Base query
    # -------------------------
    query = select(UserActivity)
    count_query = select(func.count()).select_from(UserActivity)

    # -------------------------
    # Filters
    # -------------------------
    if user_id:
        query = query.where(UserActivity.user_id == user_id)
        count_query = count_query.where(UserActivity.user_id == user_id)

    if username:
        query = query.where(UserActivity.username_snapshot.ilike(f"%{username}%"))
        count_query = count_query.where(
            UserActivity.username_snapshot.ilike(f"%{username}%")
        )

    # -------------------------
    # Sorting
    # -------------------------
    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, UserActivity.created_at)
    order_fn = desc if order.lower() == "desc" else asc
    query = query.order_by(order_fn(sort_column))

    # -------------------------
    # Pagination
    # -------------------------
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # -------------------------
    # Execute
    # -------------------------
    total = await db.scalar(count_query)
    result = await db.execute(query)

    return total or 0, result.scalars().all()