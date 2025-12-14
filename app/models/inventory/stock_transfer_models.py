from sqlalchemy import (
    Column,
    Integer,
    Enum,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.stock_transfer_status import TransferStatus


class StockTransfer(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    StockTransfer = physical stock movement between inventory locations.
    This does NOT represent sale, reservation, or deduction.
    """

    __tablename__ = "stock_transfers"

    id = Column(Integer, primary_key=True)

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity = Column(Integer, nullable=False)

    # 🔥 USE INVENTORY LOCATION TABLE (NOT ENUM)
    from_location_id = Column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    to_location_id = Column(
        Integer,
        ForeignKey("inventory_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(TransferStatus),
        nullable=False,
        default=TransferStatus.pending,
        index=True,
    )

    transferred_by_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    completed_by_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    # ----------------------------------
    # RELATIONSHIPS
    # ----------------------------------
    product = relationship("Product", lazy="joined")

    from_location = relationship(
        "InventoryLocation",
        foreign_keys=[from_location_id],
        lazy="joined",
    )

    to_location = relationship(
        "InventoryLocation",
        foreign_keys=[to_location_id],
        lazy="joined",
    )

    transferred_by = relationship(
        "User",
        foreign_keys=[transferred_by_id],
        lazy="joined",
    )

    completed_by = relationship(
        "User",
        foreign_keys=[completed_by_id],
        lazy="joined",
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_transfer_qty"),
        CheckConstraint(
            "from_location_id != to_location_id",
            name="ck_stock_transfer_location_diff",
        ),
        Index(
            "ix_stock_transfer_product_status",
            "product_id",
            "status",
        ),
    )

    def __repr__(self):
        return (
            f"<StockTransfer id={self.id} "
            f"product_id={self.product_id} "
            f"{self.from_location_id}→{self.to_location_id} "
            f"qty={self.quantity} "
            f"status={self.status}>"
        )
