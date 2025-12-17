from sqlalchemy import update
from app.models.masters.discount_models import Discount


def _expire_discount_stmt(*, today):
    """
    Expire active discounts whose end_date < today.
    Idempotent & safe for cron.
    """
    return (
        update(Discount)
        .where(
            Discount.is_deleted.is_(False),
            Discount.is_active.is_(True),
            Discount.end_date < today,
        )
        .values(
            is_active=False,
        )
        .returning(
            Discount.id,
            Discount.name,
            Discount.code,
        )
    )

from sqlalchemy import update
from datetime import date
from app.models.masters.discount_models import Discount


def _activate_discount_stmt(*, today):
    """
    Activate discounts where:
    start_date <= today <= end_date
    """
    return (
        update(Discount)
        .where(
            Discount.is_deleted.is_(False),
            Discount.is_active.is_(False),
            Discount.start_date <= today,
            Discount.end_date >= today,
        )
        .values(
            is_active=True,
        )
        .returning(
            Discount.id,
            Discount.name,
            Discount.code,
        )
    )
