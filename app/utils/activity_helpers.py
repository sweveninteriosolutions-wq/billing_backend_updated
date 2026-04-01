# app/utils/activity_helpers.py
# ERP-048 FIXED: Added `await db.flush()` after staging the UserActivity row.
#                Previously the row was added to the session but never explicitly flushed.
#                This could cause FK ordering issues if the activity row referenced an object
#                not yet flushed, and made it harder to reason about when the row was staged.
#                The flush is cheap (no round-trip if nothing else is pending) and ensures
#                the activity row is written to the transaction before the caller commits.

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.support.activity_models import UserActivity
from app.constants.activity_templates import ACTIVITY_TEMPLATES
from app.constants.activity_codes import ActivityCode


async def emit_activity(
    db: AsyncSession,
    *,
    user_id: int | None,
    username: str,
    code: ActivityCode,
    **context,
):
    template = ACTIVITY_TEMPLATES.get(code)
    if not template:
        raise ValueError(f"No activity template for code {code}")

    try:
        message = template.format(**context)
    except KeyError as e:
        raise ValueError(
            f"Missing activity context key: {e.args[0]} for {code}"
        )

    db.add(
        UserActivity(
            user_id=user_id,
            username_snapshot=username,
            message=message,
        )
    )

    # ERP-048 FIXED: Explicit flush ensures the activity row is written within the
    # current transaction and ordered correctly relative to other staged objects.
    await db.flush()
