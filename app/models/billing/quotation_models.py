from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Enum, JSON, Index, CheckConstraint, Boolean
from sqlalchemy.orm import relationship
from decimal import Decimal
from sqlalchemy.types import Date
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.quotation_status import QuotationStatus


class Quotation(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)
    quotation_number = Column(String(50), nullable=False, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(Enum(QuotationStatus), nullable=False, default=QuotationStatus.draft, index=True)
    valid_until = Column(Date, nullable=True)

    subtotal_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    is_inter_state = Column(Boolean, nullable=False)
    cgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    sgst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    igst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    cgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    sgst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    igst_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    version = Column(Integer, nullable=False, default=1)
    item_signature = Column(String(128), nullable=False, index=True)
    description = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    additional_data = Column(JSON, nullable=True)

    customer = relationship("Customer", back_populates="quotations", lazy="selectin")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_quotation_customer_status", "customer_id", "status"),
        CheckConstraint("subtotal_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="ck_quotation_amounts_non_negative"),
        CheckConstraint("(cgst_amount + sgst_amount + igst_amount) = tax_amount", name="ck_quotation_tax_breakup"),
        CheckConstraint("(is_inter_state = TRUE AND igst_amount > 0 AND cgst_amount = 0 AND sgst_amount = 0) OR (is_inter_state = FALSE AND igst_amount = 0)", name="ck_quotation_gst_type"),
    )

    def __repr__(self):
        return f"<Quotation {self.quotation_number} status={self.status}>"


class QuotationItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_name = Column(String, nullable=False)
    hsn_code = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)

    quotation = relationship("Quotation", back_populates="items", lazy="selectin")
    product = relationship("Product", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quotation_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_quotation_item_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_quotation_item_total_non_negative"),
    )

    def __repr__(self):
        return f"<QuotationItem id={self.id} product_id={self.product_id} qty={self.quantity}>"
