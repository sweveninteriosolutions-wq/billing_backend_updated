# app/schemas/inventory/warehouse_schemas.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class WarehouseCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Unique warehouse code")
    name: str = Field(..., min_length=1, max_length=150, description="Warehouse name")
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = Field(None, max_length=10)
    gstin: Optional[str] = Field(None, max_length=15)
    phone: Optional[str] = Field(None, max_length=20)
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = Field(None, max_length=10)
    gstin: Optional[str] = Field(None, max_length=15)
    phone: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    version: int


class WarehouseOut(BaseModel):
    id: int
    code: str
    name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    gstin: Optional[str]
    phone: Optional[str]
    is_active: bool
    version: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class WarehouseListItem(BaseModel):
    id: int
    code: str
    name: str
    city: Optional[str]
    state: Optional[str]
    is_active: bool
    locations_count: int = 0

    model_config = {"from_attributes": True}


class WarehouseListData(BaseModel):
    total: int
    items: list[WarehouseListItem]
