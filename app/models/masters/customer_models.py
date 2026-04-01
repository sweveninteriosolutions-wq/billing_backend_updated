from sqlalchemy import Column, Integer, String, Boolean, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Customer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)

    customer_code = Column(String(50), nullable=False, unique=True, index=True)

    name = Column(String(255), nullable=False, index=True)
    # ERP-040 FIXED: Added unique=True to enforce email uniqueness at the DB level.
    # Previously only a service-level check existed; concurrent inserts could bypass it.
    # Migration required: CREATE UNIQUE INDEX uq_customers_email ON customers(email);
    email = Column(String(255), nullable=False, index=True, unique=True)
    phone = Column(String(20), nullable=True, index=True)
    address = Column(JSON, nullable=True)
    gstin = Column(String(15), nullable=True, index=True)

    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)

    # lazy="raise" prevents accidental N+1 — must use explicit selectinload() where needed
    quotations = relationship("Quotation", back_populates="customer", lazy="raise")
    invoices = relationship("Invoice", back_populates="customer", lazy="raise")
    loyalty_tokens = relationship("LoyaltyToken", back_populates="customer", lazy="raise")
    complaints = relationship("Complaint", back_populates="customer", lazy="raise")

    __table_args__ = (
        Index("ix_customer_active", "is_active"),
        # ERP-040: Explicit unique constraint name for clean migration rollback
        UniqueConstraint("email", name="uq_customers_email"),
    )

    def __repr__(self):
        return f"<Customer id={self.id} code={self.customer_code} name={self.name} active={self.is_active}>"
