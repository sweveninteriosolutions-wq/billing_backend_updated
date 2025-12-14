# app/models/grn_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
  Numeric,
    ForeignKey,
    CheckConstraint,
    Index
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class GRN(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "grns"

    id = Column(Integer, primary_key=True)

    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id"), nullable=False, index=True)

    purchase_order = Column(String(100), nullable=True)
    bill_number = Column(String(100), nullable=True)
    bill_file = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    status = Column(String(50), nullable=False, default="draft")  # draft → verified → cancelled

    version = Column(Integer, nullable=False, default=1)

    supplier = relationship("Supplier", back_populates="grns", lazy="joined")
    items = relationship("GRNItem", back_populates="grn", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_grn_supplier_status", "supplier_id", "status"),
    )

    def __repr__(self):
        return f"<GRN id={self.id} status={self.status}>"

class GRNItem(Base):
    __tablename__ = "grn_items"

    id = Column(Integer, primary_key=True)

    grn_id = Column(Integer, ForeignKey("grns.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)

    grn = relationship("GRN", back_populates="items", lazy="joined")
    product = relationship("Product", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_grn_item_quantity_positive"
        ),
        CheckConstraint(
            "unit_cost >= 0",
            name="check_grn_item_cost_non_negative"
        ),
        Index(
            "ix_grn_item_grn_product",
            "grn_id",
            "product_id"
        ),
    )

    def __repr__(self):
        return (
            f"<GRNItem id={self.id} "
            f"product_id={self.product_id} "
            f"qty={self.quantity}>"
        )