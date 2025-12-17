from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Enum, JSON, Index, CheckConstraint, Boolean
from sqlalchemy.orm import relationship
from decimal import Decimal
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.invoice_status import InvoiceStatus


class Invoice(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_number = Column(String(50), nullable=False, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.draft, index=True)
    version = Column(Integer, nullable=False, default=1)

    gross_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_paid = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    balance_due = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    is_inter_state = Column(Boolean, nullable=False)
    cgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    sgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    igst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    customer_snapshot = Column(JSON, nullable=False, default=dict)
    item_signature = Column(String(128), nullable=False, index=True)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    customer = relationship("Customer", back_populates="invoices", lazy="selectin")
    quotation = relationship("Quotation", lazy="selectin")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")
    loyalty_tokens = relationship("LoyaltyToken", back_populates="invoice", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_invoice_customer_status", "customer_id", "status"),
        CheckConstraint("gross_amount >= 0 AND tax_amount >= 0 AND net_amount >= 0", name="ck_invoice_amounts_non_negative"),
        CheckConstraint("(cgst_amount + sgst_amount + igst_amount) = tax_amount", name="ck_invoice_tax_breakup"),
        CheckConstraint("(is_inter_state = TRUE AND igst_amount > 0 AND cgst_amount = 0 AND sgst_amount = 0) OR (is_inter_state = FALSE AND igst_amount = 0)", name="ck_invoice_gst_type"),
        CheckConstraint("total_paid + balance_due = net_amount", name="ck_invoice_payment_consistency"),
    )

    def __repr__(self):
        return f"<Invoice {self.invoice_number} status={self.status}>"


class InvoiceItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="items", lazy="selectin")
    product = relationship("Product", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_item_qty_positive"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_item_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_invoice_item_total_non_negative"),
    )

    def __repr__(self):
        return f"<InvoiceItem id={self.id} product_id={self.product_id} qty={self.quantity} total={self.line_total}>"
