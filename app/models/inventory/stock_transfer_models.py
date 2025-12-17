from sqlalchemy import Column, Integer, Enum, ForeignKey, CheckConstraint, Index, String
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.stock_transfer_status import TransferStatus


class StockTransfer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """Physical stock movement between inventory locations. NOT a sale, reservation, or deduction."""

    __tablename__ = "stock_transfers"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    from_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    to_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(Enum(TransferStatus), nullable=False, default=TransferStatus.pending, index=True)
    transferred_by_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    completed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    item_signature = Column(String(128), nullable=False, index=True)

    product = relationship("Product", lazy="selectin")
    from_location = relationship("InventoryLocation", foreign_keys=[from_location_id], lazy="selectin")
    to_location = relationship("InventoryLocation", foreign_keys=[to_location_id], lazy="selectin")
    transferred_by = relationship("User", foreign_keys=[transferred_by_id], lazy="selectin")
    completed_by = relationship("User", foreign_keys=[completed_by_id], lazy="selectin")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_transfer_qty_positive"),
        CheckConstraint("from_location_id != to_location_id", name="ck_stock_transfer_location_diff"),
        Index("ix_stock_transfer_product_status", "product_id", "status"),
        Index("ix_stock_transfer_location_status", "from_location_id", "to_location_id", "status"),
    )

    def __repr__(self):
        return f"<StockTransfer id={self.id} product_id={self.product_id} {self.from_location_id}->{self.to_location_id} qty={self.quantity} status={self.status}>"
