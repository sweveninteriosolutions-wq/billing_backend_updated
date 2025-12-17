from sqlalchemy import Column, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, AuditMixin


class InventoryBalance(Base, TimestampMixin, AuditMixin):
    __tablename__ = "inventory_balances"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), primary_key=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="RESTRICT"), primary_key=True)
    quantity = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="inventory_balances", lazy="selectin")
    location = relationship("InventoryLocation", back_populates="inventory_balances", lazy="selectin")

    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_inventory_balance_quantity_non_negative"),)

    def __repr__(self):
        return f"<InventoryBalance product_id={self.product_id} location_id={self.location_id} qty={self.quantity}>"
