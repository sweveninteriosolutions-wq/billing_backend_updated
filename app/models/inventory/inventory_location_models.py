from sqlalchemy import Column, Integer, String, Boolean, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class InventoryLocation(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "inventory_locations"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True, index=True)  # business identifier (warehouse, showroom, etc.)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)

    inventory_balances = relationship("InventoryBalance", back_populates="location", lazy="selectin")
    inventory_movements = relationship("InventoryMovement", back_populates="location", lazy="selectin")

    __table_args__ = (Index("ix_inventory_location_active", "is_active"),)

    def __repr__(self):
        return f"<InventoryLocation id={self.id} code={self.code} active={self.is_active}>"
