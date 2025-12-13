# app/schemas/inventory/inventory_balance_schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class InventoryBalanceTableSchema(BaseModel):
    product_id: int
    product_name: str
    sku: str

    location_id: int
    location_code: str

    quantity: int
    min_stock_threshold: int

    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class InventoryBalanceListResponseSchema(BaseModel):
    msg: str
    total: int
    data: list[InventoryBalanceTableSchema]
