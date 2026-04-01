# app/models/inventory/purchase_order_models.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Numeric, Date, Index, CheckConstraint
from sqlalchemy.orm import relationship
from decimal import Decimal
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class PurchaseOrder(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    Purchase Order placed with a supplier.
    Status lifecycle: draft -> submitted -> approved -> partial -> fulfilled -> cancelled
    """
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    po_number = Column(String(60), nullable=False, unique=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="draft", index=True)
    # draft | submitted | approved | partial | fulfilled | cancelled

    expected_date = Column(Date, nullable=True)
    approved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    notes = Column(Text, nullable=True)

    gross_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    tax_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    net_amount = Column(Numeric(14, 2), nullable=False, default=Decimal("0.00"))

    version = Column(Integer, nullable=False, default=1)

    supplier = relationship("Supplier", back_populates="purchase_orders", lazy="selectin")
    location = relationship("InventoryLocation", lazy="selectin")
    approved_by = relationship("User", foreign_keys=[approved_by_id], lazy="selectin")
    items = relationship("PurchaseOrderItem", back_populates="po", cascade="all, delete-orphan", lazy="selectin")
    grns = relationship("GRN", back_populates="purchase_order_rel", lazy="selectin")

    __table_args__ = (
        Index("ix_po_supplier_status", "supplier_id", "status"),
        Index("ix_po_location_status", "location_id", "status"),
        CheckConstraint("gross_amount >= 0 AND net_amount >= 0", name="ck_po_amounts_non_negative"),
    )

    def __repr__(self):
        return f"<PurchaseOrder {self.po_number} status={self.status}>"


class PurchaseOrderItem(Base, TimestampMixin):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)

    quantity_ordered = Column(Integer, nullable=False)
    quantity_received = Column(Integer, nullable=False, default=0)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)

    po = relationship("PurchaseOrder", back_populates="items", lazy="selectin")
    product = relationship("Product", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity_ordered > 0", name="ck_po_item_qty_positive"),
        CheckConstraint("quantity_received >= 0", name="ck_po_item_received_non_negative"),
        CheckConstraint("quantity_received <= quantity_ordered", name="ck_po_item_received_lte_ordered"),
        CheckConstraint("unit_cost >= 0", name="ck_po_item_cost_non_negative"),
        Index("ix_po_item_po_product", "po_id", "product_id"),
    )

    def __repr__(self):
        return f"<POItem id={self.id} product_id={self.product_id} qty={self.quantity_ordered}>"
