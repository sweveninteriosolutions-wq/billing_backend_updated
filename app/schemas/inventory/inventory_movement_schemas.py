# app/schemas/inventory/inventory_movement_schemas.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class InventoryMovementOut(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    location_id: int
    location_name: Optional[str] = None
    quantity_change: int
    reference_type: str
    reference_id: int

    created_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class InventoryMovementListData(BaseModel):
    total: int
    items: List[InventoryMovementOut]
