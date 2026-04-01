# app/services/billing/quotation_expiry_core.py
# ERP-016 FIXED: Replaced `is_deleted == False` with `.is_(False)` for NULL-safe comparison.

from sqlalchemy import update
from app.models.billing.quotation_models import Quotation
from app.models.enums.quotation_status import QuotationStatus


def _expire_quotation_stmt(extra_where=None, updated_by_id=None):
    where_clause = [
        Quotation.status == QuotationStatus.approved,
        Quotation.is_deleted.is_(False),   # ERP-016 fixed: was `== False`
    ]

    if extra_where is not None:
        where_clause.extend(extra_where)

    return (
        update(Quotation)
        .where(*where_clause)
        .values(
            status=QuotationStatus.expired,
            version=Quotation.version + 1,
            updated_by_id=updated_by_id,
        )
        .returning(Quotation)
    )
