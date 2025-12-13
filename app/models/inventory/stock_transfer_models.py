# app/models/stock_transfer_models.py

from sqlalchemy import (
    Column,
    Integer,
    Enum,
    ForeignKey,
    CheckConstraint,
    Index
)
from sqlalchemy.orm import relationship
import enum

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.stock_transfer_status import InventoryLocation, TransferStatus




class StockTransfer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    StockTransfer = physical stock movement between locations.
    This does NOT represent sale, reservation, or deduction.
    """

    __tablename__ = "stock_transfers"

    id = Column(Integer, primary_key=True)

    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)

    from_location = Column(Enum(InventoryLocation), nullable=False)
    to_location = Column(Enum(InventoryLocation), nullable=False)

    status = Column(Enum(TransferStatus), nullable=False, default=TransferStatus.pending, index=True)

    transferred_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    completed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    product = relationship("Product", lazy="joined")
    transferred_by = relationship("User", foreign_keys=[transferred_by_id], lazy="joined")
    completed_by = relationship("User", foreign_keys=[completed_by_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_transfer_qty"),
        CheckConstraint(
            "from_location != to_location",
            name="ck_stock_transfer_location_diff"
        ),
        Index("ix_stock_transfer_product_status", "product_id", "status"),
    )

    def __repr__(self):
        return (
            f"<StockTransfer id={self.id} "
            f"product_id={self.product_id} "
            f"{self.from_location}→{self.to_location} "
            f"qty={self.quantity} "
            f"status={self.status}>"
        )
