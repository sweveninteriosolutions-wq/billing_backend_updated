# app/schemas/inventory/location_schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class InventoryLocationCreateSchema(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)


class InventoryLocationUpdateSchema(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    version: int


class InventoryLocationTableSchema(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: Optional[datetime]

    created_by_id: Optional[int]
    updated_by_id: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    class Config:
        from_attributes = True


class InventoryLocationResponseSchema(BaseModel):
    msg: str
    data: InventoryLocationTableSchema


class InventoryLocationListResponseSchema(BaseModel):
    msg: str
    total: int
    data: list[InventoryLocationTableSchema]
