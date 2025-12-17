# app/schemas/masters/product_schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


class ProductCreate(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    price: Decimal = Field(gt=0)
    min_stock_threshold: int = Field(ge=0)
    supplier_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0)
    min_stock_threshold: Optional[int] = Field(default=None, ge=0)
    supplier_id: Optional[int] = None

    version: int


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: Optional[str]
    price: Decimal
    min_stock_threshold: int
    supplier_id: Optional[int]

    is_active: bool
    version: int

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProductListData(BaseModel):
    total: int
    items: List[ProductOut]


class VersionPayload(BaseModel):
    version: int
