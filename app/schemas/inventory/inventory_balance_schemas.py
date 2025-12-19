from pydantic import BaseModel
from typing import Optional, List
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

class InventoryBalanceListData(BaseModel):
    total: int
    items: List[InventoryBalanceTableSchema]
