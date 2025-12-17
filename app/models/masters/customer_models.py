from sqlalchemy import Column, Integer, String, Boolean, JSON, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Customer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)

    customer_code = Column(String(50), nullable=False, unique=True, index=True)

    name = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    address = Column(JSON, nullable=True)
    gstin = Column(String(15), nullable=True, index=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)

    quotations = relationship("Quotation", back_populates="customer", lazy="selectin")
    invoices = relationship("Invoice", back_populates="customer", lazy="selectin")
    loyalty_tokens = relationship("LoyaltyToken", back_populates="customer", lazy="selectin")
    complaints = relationship("Complaint", back_populates="customer", lazy="selectin")

    __table_args__ = (Index("ix_customer_active", "is_active"),)

    def __repr__(self):
        return f"<Customer id={self.id} code={self.customer_code} name={self.name} active={self.is_active}>"
