# app/models/customer_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    JSON,
    Index
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Customer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=True)

    address = Column(JSON, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    version = Column(Integer, nullable=False, default=1)
    
    # quotations = relationship("Quotation", back_populates="customer", lazy="selectin")
    # sales_orders = relationship("SalesOrder", back_populates="customer", lazy="selectin")
    # invoices = relationship("Invoice", back_populates="customer", lazy="selectin")
    # payments = relationship("Payment", back_populates="customer", lazy="selectin")
    # loyalty_tokens = relationship("LoyaltyToken", back_populates="customer", lazy="selectin")
    # complaints = relationship("Complaint", back_populates="customer", lazy="selectin")

    __table_args__ = (
        Index("ix_customer_email", "email"),
        Index("ix_customer_phone", "phone"),
        Index("ix_customer_active", "is_active"),
    )

    def __repr__(self):
        return (
            f"<Customer id={self.id} "
            f"name={self.name} "
            f"email={self.email} "
            f"active={self.is_active}>"
        )
