# app/models/inventory/inventory_balance_view.py

from sqlalchemy import Column, Integer, String, DateTime
from app.core.db import Base

class InventoryBalanceView(Base):
    __tablename__ = "inventory_balance_view"
    __table_args__ = {"extend_existing": True}

    product_id = Column(Integer, primary_key=True)
    location_id = Column(Integer, primary_key=True)

    quantity = Column(Integer)

    product_name = Column(String)
    sku = Column(String)
    min_stock_threshold = Column(Integer)  # 👈 THIS MUST EXIST
    location_code = Column(String)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)
