from sqlalchemy import Column, Integer, Numeric, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin

class LoyaltyToken(Base, TimestampMixin, AuditMixin):
    __tablename__ = "loyalty_tokens"

    id = Column(Integer, primary_key=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)

    tokens = Column(Integer, nullable=False)

    customer = relationship("Customer", back_populates="loyalty_tokens", lazy="joined")
    invoice = relationship("Invoice", back_populates="loyalty_tokens", lazy="joined")

    def __repr__(self):
        return f"<LoyaltyToken id={self.id} tokens={self.tokens}>"
