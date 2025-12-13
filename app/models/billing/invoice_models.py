# app/models/invoice_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Numeric,
    Enum,
    Index,
    JSON,
    CheckConstraint,
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
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=True, index=True)
    discount_id = Column(Integer, ForeignKey("discounts.id"), nullable=True, index=True)

    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.draft)

    gross_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_paid = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    balance_due = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    customer_snapshot = Column(JSON, nullable=False)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    customer = relationship("Customer", back_populates="invoices", lazy="joined")
    quotation = relationship("Quotation", back_populates="invoices", lazy="joined")
    sales_order = relationship("SalesOrder", back_populates="invoices", lazy="joined")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    loyalty_tokens = relationship("LoyaltyToken", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    discount = relationship("Discount", back_populates="invoices", lazy="joined")

    __table_args__ = (
        Index("ix_invoice_customer_status", "customer_id", "status"),
    )

    def __repr__(self):
        return (
            f"<Invoice id={self.id} "
            f"number={self.invoice_number} "
            f"status={self.status}>"
        )

class InvoiceItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)

    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    sales_order_item_id = Column(Integer, ForeignKey("sales_order_items.id"), nullable=True, index=True)

    quantity = Column(Integer, nullable=False)

    unit_price = Column(Numeric(12, 2), nullable=False)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_total = Column(Numeric(14, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items", lazy="joined")
    product = relationship("Product", lazy="joined")
    sales_order_item = relationship("SalesOrderItem", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_item_qty"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_item_price"),
        Index("ix_invoice_item_invoice_product", "invoice_id", "product_id"),
    )

    def __repr__(self):
        return (
            f"<InvoiceItem id={self.id} "
            f"product_id={self.product_id} "
            f"qty={self.quantity} "
            f"total={self.line_total}>"
        )

