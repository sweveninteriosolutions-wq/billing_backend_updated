# app/schemas/masters/product_schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal
from datetime import datetime


# -----------------------
# REQUEST SCHEMAS
# -----------------------

class ProductCreateSchema(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    price: Decimal = Field(gt=0)
    min_stock_threshold: int = Field(ge=0)
    supplier_id: Optional[int] = None


class ProductUpdateSchema(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0)
    min_stock_threshold: Optional[int] = Field(default=None, ge=0)
    supplier_id: Optional[int] = None

    version: int


# -----------------------
# RESPONSE SCHEMAS
# -----------------------

class ProductTableSchema(BaseModel):
    id: int
    sku: str
    name: str
    category: Optional[str]
    price: Decimal
    min_stock_threshold: int
    supplier_id: Optional[int]

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


class ProductResponseSchema(BaseModel):
    msg: str
    data: Optional[ProductTableSchema] = None


class ProductListResponseSchema(BaseModel):
    msg: str
    total: int
    data: List[ProductTableSchema]
