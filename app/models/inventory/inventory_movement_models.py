# app/models/inventory_movement_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    CheckConstraint,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class InventoryMovement(Base, TimestampMixin, AuditMixin):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id"), nullable=False, index=True)

    quantity_change = Column(Integer, nullable=False)  # +ve = stock in, -ve = stock out
    reference_type = Column(String(50), nullable=False)  # GRN, INVOICE, TRANSFER, ADJUSTMENT
    
    reference_id = Column(Integer, nullable=False)

    product = relationship("Product", back_populates="inventory_movements", lazy="joined")
    location = relationship("InventoryLocation", back_populates="inventory_movements", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "quantity_change <> 0",
            name="check_inventory_quantity_non_zero"
        ),
        Index(
            "ix_inventory_movement_product_location",
            "product_id",
            "location_id"
        ),
        Index(
            "ix_inventory_movement_reference",
            "reference_type",
            "reference_id"
        ),
    )

    def __repr__(self):
        return (
            f"<InventoryMovement id={self.id} "
            f"product_id={self.product_id} "
            f"location_id={self.location_id} "
            f"qty={self.quantity_change} "
            f"ref={self.reference_type}:{self.reference_id}>"
        )
