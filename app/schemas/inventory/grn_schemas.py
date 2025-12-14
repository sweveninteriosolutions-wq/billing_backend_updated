from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

class GRNItemCreateSchema(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, description="Received quantity")
    unit_cost: Decimal = Field(ge=0, description="Cost per unit")

class GRNItemTableSchema(BaseModel):
    product_id: int
    quantity: int
    unit_cost: Decimal

class GRNCreateSchema(BaseModel):
    supplier_id: int
    purchase_order: Optional[str] = None
    bill_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[GRNItemCreateSchema]

class GRNTableSchema(BaseModel):
    id: int
    supplier_id: Optional[int]

    purchase_order: Optional[str]
    bill_number: Optional[str]
    notes: Optional[str]

    status: str
    created_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]


    items: List[GRNItemTableSchema]
    version: int

    class Config:
        from_attributes = True

class GRNResponseSchema(BaseModel):
    msg: str
    data: GRNTableSchema

class GRNListResponseSchema(BaseModel):
    msg: str
    total: int
    data: List[GRNTableSchema]

class GRNItemUpdateSchema(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)

class GRNUpdateSchema(BaseModel):
    supplier_id: Optional[int] = None
    purchase_order: Optional[str] = None
    bill_number: Optional[str] = None
    notes: Optional[str] = None
    version: int
    items: List[GRNItemUpdateSchema]



