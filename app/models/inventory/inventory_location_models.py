# app/models/inventory_location_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Index
)
from app.core.db import Base
from sqlalchemy.orm import relationship
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class InventoryLocation(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "inventory_locations"

    id = Column(Integer, primary_key=True)

    code = Column(String(50), unique=True, nullable=False)  # e.g. showroom, warehouse
    name = Column(String(100), nullable=False)  # Display name

    is_active = Column(Boolean, default=True, nullable=False)

    inventory_balances = relationship("InventoryBalance", back_populates="location", lazy="selectin")
    inventory_movements = relationship("InventoryMovement", back_populates="location", lazy="selectin")

    __table_args__ = (
        Index("ix_inventory_location_code", "code"),
        Index("ix_inventory_location_active", "is_active"),
    )

    def __repr__(self):
        return (
            f"<InventoryLocation id={self.id} "
            f"code={self.code} "
            f"active={self.is_active}>"
        )
