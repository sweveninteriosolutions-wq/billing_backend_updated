from sqlalchemy import (
    Column, Integer, String, ForeignKey, Numeric,
    Enum, Index, JSON, CheckConstraint
)
from sqlalchemy.orm import relationship
from decimal import Decimal

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.invoice_status import InvoiceStatus


class Invoice(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=True, index=True)

    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.draft)
    version = Column(Integer, nullable=False, default=1)

    gross_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"),)
    
    discount_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    total_paid = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    balance_due = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    customer_snapshot = Column(JSON, nullable=False, default=dict)
    
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    quotation = relationship("Quotation", lazy="selectin")
    customer = relationship("Customer", back_populates="invoices", lazy="selectin")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    loyalty_tokens = relationship("LoyaltyToken", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_invoice_customer_status", "customer_id", "status"),
        Index("ix_invoice_status", "status"),
    )

    def __repr__(self):
        return (
            f"<Invoice id={self.id} "
            f"number={self.invoice_number} "
            f"status={self.status.value}>"
        )


class InvoiceItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", lazy="selectin")


    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_item_qty"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_item_price"),
    )

    def __repr__(self):
        return (
            f"<InvoiceItem id={self.id} "
            f"product_id={self.product_id} "
            f"qty={self.quantity} "
            f"total={self.line_total}>"
        )
