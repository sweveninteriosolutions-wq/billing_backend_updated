from sqlalchemy import Column, Integer, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class LoyaltyToken(Base, TimestampMixin, AuditMixin):
    __tablename__ = "loyalty_tokens"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    tokens = Column(Integer, nullable=False)

    customer = relationship("Customer", back_populates="loyalty_tokens", lazy="selectin")
    invoice = relationship("Invoice", back_populates="loyalty_tokens", lazy="selectin")

    __table_args__ = (
        CheckConstraint("tokens > 0", name="ck_loyalty_tokens_positive"),
        Index("ix_loyalty_customer_invoice", "customer_id", "invoice_id"),
    )

    def __repr__(self):
        return f"<LoyaltyToken id={self.id} customer_id={self.customer_id} invoice_id={self.invoice_id} tokens={self.tokens}>"
