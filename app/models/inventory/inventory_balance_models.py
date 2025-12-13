# app/models/inventory_balance_models.py

from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class InventoryBalance(Base, TimestampMixin, AuditMixin):
    __tablename__ = "inventory_balances"

    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="inventory_balances", lazy="joined")
    location = relationship("InventoryLocation", back_populates="inventory_balances", lazy="joined")

    __table_args__ = (
        Index(
            "ix_inventory_balance_product",
            "product_id"
        ),
        Index(
            "ix_inventory_balance_location",
            "location_id"
        ),
    )

    def __repr__(self):
        return (
            f"<InventoryBalance "
            f"product_id={self.product_id} "
            f"location_id={self.location_id} "
            f"qty={self.quantity}>"
        )
