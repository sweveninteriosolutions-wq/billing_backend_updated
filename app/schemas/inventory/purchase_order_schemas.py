# app/schemas/inventory/purchase_order_schemas.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: str})


# =====================================================
# ITEM INPUTS
# =====================================================
class POItemCreate(BaseModel):
    product_id: int
    quantity_ordered: int = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


# =====================================================
# CREATE
# =====================================================
class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    location_id: int
    expected_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[POItemCreate]


# =====================================================
# UPDATE
# =====================================================
class PurchaseOrderUpdate(BaseModel):
    version: int
    expected_date: Optional[date] = None
    notes: Optional[str] = None
    items: List[POItemCreate]


# =====================================================
# ITEM OUTPUT
# =====================================================
class POItemOut(ORMBase):
    id: int
    product_id: int
    product_name: Optional[str] = None
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    line_total: Decimal


# =====================================================
# SINGLE PO OUTPUT
# =====================================================
class PurchaseOrderOut(ORMBase):
    id: int
    po_number: str
    supplier_id: int
    supplier_name: Optional[str] = None
    location_id: int
    location_name: Optional[str] = None
    status: str
    expected_date: Optional[date]
    notes: Optional[str]
    gross_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    version: int
    created_at: datetime
    updated_at: Optional[datetime]
    items: List[POItemOut]


# =====================================================
# LIST ITEM
# =====================================================
class PurchaseOrderListItem(BaseModel):
    id: int
    po_number: str
    supplier_name: str
    location_name: str
    status: str
    net_amount: Decimal
    expected_date: Optional[date]
    items_count: int
    created_at: datetime


class PurchaseOrderListData(BaseModel):
    total: int
    items: List[PurchaseOrderListItem]
