from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Product(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), nullable=False, unique=True, index=True)
    hsn_code = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True, unique=True)
    category = Column(String(100), nullable=True, index=True)
    description = Column(String(500), nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    min_stock_threshold = Column(Integer, default=0, nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)

    supplier = relationship("Supplier", back_populates="products", lazy="selectin")
    inventory_balances = relationship("InventoryBalance", back_populates="product", lazy="selectin")
    inventory_movements = relationship("InventoryMovement", back_populates="product", lazy="selectin")

    __table_args__ = (Index("ix_product_name_category", "name", "category"),)

    def __repr__(self):
        return f"<Product id={self.id} sku={self.sku} name={self.name}>"
