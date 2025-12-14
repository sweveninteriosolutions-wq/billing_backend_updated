from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing.quotation_models import Quotation
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode
from app.services.billing.quotation_expiry_core import _expire_quotation_stmt


async def auto_expire_quotations(db: AsyncSession):
    today = date.today()

    stmt = _expire_quotation_stmt(
        extra_where=[
            Quotation.valid_until.isnot(None),
            Quotation.valid_until < today,
        ],
        updated_by_id=None,  # system action
    )

    result = await db.execute(stmt)
    expired = result.scalars().all()

    if not expired:
        return 0

    for q in expired:
        await emit_activity(
            db,
            user_id=None,
            username="system",
            code=ActivityCode.EXPIRE_QUOTATION,
            actor_role="System",
            actor_email="system",
            target_name=q.quotation_number,
            changes=f"Expired automatically on {today}",
        )

    await db.commit()
    return len(expired)
