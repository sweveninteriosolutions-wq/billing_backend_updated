# app/models/inventory/warehouse_models.py
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
# location_type is a free-form string enum kept flexible for now
# Values: WAREHOUSE | SHOWROOM | TRANSIT


class Warehouse(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    Formal Warehouse / Location entity.
    Each InventoryLocation can belong to a Warehouse.
    """
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False, unique=True, index=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    gstin = Column(String(15), nullable=True)
    phone = Column(String(20), nullable=True)
    # WAREHOUSE | SHOWROOM | TRANSIT
    location_type = Column(String(20), nullable=False, default="WAREHOUSE")
    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)

    locations = relationship("InventoryLocation", back_populates="warehouse", lazy="selectin")

    __table_args__ = (Index("ix_warehouse_active", "is_active"),)

    def __repr__(self):
        return f"<Warehouse id={self.id} code={self.code} name={self.name}>"
