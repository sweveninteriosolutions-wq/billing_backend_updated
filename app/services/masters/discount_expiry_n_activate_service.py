# app/services/masters/discount_expiry_n_activate_service.py
# ERP-047 NOTE: These two functions are now called from SEPARATE scheduler jobs,
#               each with their own isolated AsyncSessionLocal session (fixed in ERP-043).
#               So a failure in auto_activate_discounts cannot corrupt the committed
#               state of auto_expire_discounts, and vice versa.
#               The functions themselves each own their commit — this is intentional
#               since they are independent operations with independent audit trails.

from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.masters.discount_expiry_n_activate_core import (
    _expire_discount_stmt,
    _activate_discount_stmt,
)
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode


async def auto_expire_discounts(db: AsyncSession) -> int:
    """
    Expire all active discounts whose end_date is in the past.
    Returns the count of discounts expired.
    """
    today = date.today()
    stmt = _expire_discount_stmt(today=today)
    result = await db.execute(stmt)
    expired = result.all()

    if not expired:
        return 0

    for d in expired:
        await emit_activity(
            db=db,
            user_id=None,
            username="system",
            code=ActivityCode.EXPIRE_DISCOUNT,
            actor_role="System",
            actor_email="system",
            target_name=d.name,
            target_code=d.code,
            changes=f"Expired automatically on {today}",
        )

    await db.commit()
    return len(expired)


async def auto_activate_discounts(db: AsyncSession) -> int:
    """
    Activate all inactive discounts whose start_date has arrived and end_date is in the future.
    Returns the count of discounts activated.
    """
    today = date.today()
    stmt = _activate_discount_stmt(today=today)
    result = await db.execute(stmt)
    activated = result.all()

    if not activated:
        return 0

    for d in activated:
        await emit_activity(
            db=db,
            user_id=None,
            username="system",
            code=ActivityCode.ACTIVATE_DISCOUNT,
            actor_role="System",
            actor_email="system",
            target_name=d.name,
            target_code=d.code,
            changes=f"Auto-activated on {today}",
        )

    await db.commit()
    return len(activated)
