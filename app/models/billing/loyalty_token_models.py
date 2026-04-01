# app/models/billing/loyalty_token_models.py
# ERP-038 FIXED: Renamed from loyaltyTokens_models.py → loyalty_token_models.py
#                (snake_case, consistent with all other model files).
# ERP-039 FIXED: Changed relationship lazy= from "noload" to "raise" on customer and invoice.
#                "noload" silently returns None even when the row exists — this causes
#                hard-to-debug None values in API responses and business logic.
#                "raise" forces all callers to be explicit with selectinload(), making
#                the access pattern visible and preventing silent data loss.

from sqlalchemy import Column, Integer, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class LoyaltyToken(Base, TimestampMixin, AuditMixin):
    __tablename__ = "loyalty_tokens"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"),
                         nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    tokens = Column(Integer, nullable=False)

    # ERP-039 FIXED: lazy="raise" — callers must use selectinload() explicitly.
    # Previously "noload" silently returned None, masking missing joins.
    customer = relationship("Customer", back_populates="loyalty_tokens", lazy="raise")
    invoice = relationship("Invoice", back_populates="loyalty_tokens", lazy="raise")

    __table_args__ = (
        CheckConstraint("tokens > 0", name="ck_loyalty_tokens_positive"),
        Index("ix_loyalty_customer_invoice", "customer_id", "invoice_id"),
    )

    def __repr__(self):
        return (
            f"<LoyaltyToken id={self.id} customer_id={self.customer_id} "
            f"invoice_id={self.invoice_id} tokens={self.tokens}>"
        )
