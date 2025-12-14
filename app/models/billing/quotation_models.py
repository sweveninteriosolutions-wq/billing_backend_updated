# app/models/quotation_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Numeric,
    Enum,
    JSON,
    Index,
    CheckConstraint
)
from sqlalchemy.orm import relationship
from decimal import Decimal
from sqlalchemy.types import Date

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.quotation_status import QuotationStatus


class Quotation(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)

    quotation_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    status = Column(
        Enum(QuotationStatus),
        nullable=False,
        default=QuotationStatus.draft
    )

    valid_until = Column(Date, nullable=True)

    subtotal_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    total_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    version = Column(Integer, nullable=False, default=1)
    item_signature = Column(String(128), index=True, nullable=False)

    description = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    additional_data = Column(JSON, nullable=True)

    customer = relationship(
        "Customer",
        back_populates="quotations",
        lazy="joined",
    )
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # invoices = relationship("Invoice", back_populates="quotation", lazy="selectin")

    __table_args__ = (
        Index(
            "ix_quotation_customer_status",
            "customer_id",
            "status"
        ),
    )

    def __repr__(self):
        return (
            f"<Quotation id={self.id} "
            f"number={self.quotation_number} "
            f"status={self.status}>"
        )

class QuotationItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True)

    quotation_id = Column(
        Integer,
        ForeignKey("quotations.id", ondelete="CASCADE"),
        nullable=False
    )

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    product_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)

    quotation = relationship("Quotation", back_populates="items", lazy="joined")

    product = relationship("Product", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_quotation_item_quantity_positive"
        ),
        Index(
            "ix_quotation_item_quotation",
            "quotation_id"
        ),
    )

    def __repr__(self):
        return (
            f"<QuotationItem id={self.id} "
            f"product_id={self.product_id} "
            f"qty={self.quantity}>"
        )
