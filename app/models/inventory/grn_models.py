from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index, CheckConstraint, Numeric
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class GRN(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "grns"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
                         nullable=False, index=True)

    # ERP-042 FIXED: Two purchase_order fields existed side-by-side:
    #   - purchase_order_id (FK to purchase_orders table) — the canonical FK column
    #   - purchase_order    (String free-text) — legacy field kept for backward compat
    #
    # Resolution: purchase_order_id is the single source of truth going forward.
    # The free-text `purchase_order` column is marked deprecated here and should be
    # removed in a future migration once all existing data has been migrated to use
    # the FK. New code must use purchase_order_id / purchase_order_rel only.
    purchase_order_id = Column(
        Integer,
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to purchase_orders. Use this field; purchase_order (text) is deprecated.",
    )
    # DEPRECATED — free-text field retained for backward compat only.
    # Do not write to this field in new code. Remove after data migration.
    purchase_order = Column(
        String(100),
        nullable=True,
        comment="DEPRECATED: legacy free-text PO reference. Use purchase_order_id instead.",
    )

    bill_number = Column(String(100), nullable=True, index=True)
    bill_file = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    version = Column(Integer, nullable=False, default=1)
    item_signature = Column(String(128), nullable=False, index=True)

    supplier = relationship("Supplier", back_populates="grns", lazy="selectin")
    # ERP-042: Canonical FK relationship — use this in all new code.
    purchase_order_rel = relationship("PurchaseOrder", back_populates="grns", lazy="selectin")
    items = relationship("GRNItem", back_populates="grn", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_grn_supplier_status", "supplier_id", "status"),
        Index("ix_grn_location_status", "location_id", "status"),
    )

    def __repr__(self):
        return f"<GRN id={self.id} status={self.status}>"


class GRNItem(Base):
    __tablename__ = "grn_items"

    id = Column(Integer, primary_key=True)
    grn_id = Column(Integer, ForeignKey("grns.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"),
                        nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)

    grn = relationship("GRN", back_populates="items", lazy="selectin")
    product = relationship("Product", lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_grn_item_quantity_positive"),
        CheckConstraint("unit_cost >= 0", name="ck_grn_item_unit_cost_non_negative"),
        Index("ix_grn_item_grn_product", "grn_id", "product_id"),
    )

    def __repr__(self):
        return f"<GRNItem id={self.id} product_id={self.product_id} qty={self.quantity}>"
