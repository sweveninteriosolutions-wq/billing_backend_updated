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

    message = template.format(**context)

    db.add(
        UserActivity(
            user_id=user_id,
            username_snapshot=username,
            message=message,
        )
    )

    await db.commit()
