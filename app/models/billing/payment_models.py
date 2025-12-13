from sqlalchemy import Column, Integer, Numeric, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin

class Payment(Base, TimestampMixin, AuditMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True )

    amount = Column(Numeric(14, 2), nullable=False)
    payment_method = Column(String(50), nullable=True)

    invoice = relationship("Invoice", back_populates="payments", lazy="joined")


    def __repr__(self):
        return f"<Payment id={self.id} amount={self.amount}>"
