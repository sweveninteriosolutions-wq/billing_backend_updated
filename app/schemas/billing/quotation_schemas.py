# app/schemas/billing/quotation_schemas.py

from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date

# ---------------- ITEM ----------------

class QuotationItemCreate(BaseModel):
    product_id: int
    quantity: int

class QuotationItemUpdate(BaseModel):
    product_id: int
    quantity: int

class QuotationItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal

# ---------------- QUOTATION ----------------

class QuotationCreate(BaseModel):
    customer_id: int
    items: List[QuotationItemCreate]
    valid_until: Optional[date] = None
    description: Optional[str] = None
    notes: Optional[str] = None

class QuotationUpdate(BaseModel):
    description: Optional[str] = None
    notes: Optional[str] = None
    valid_until: Optional[date] = None
    items: Optional[List[QuotationItemUpdate]] = None
    version: int

class QuotationOut(BaseModel):
    id: int
    quotation_number: str
    customer_id: int
    status: str

    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    valid_until: Optional[date]
    description: Optional[str]
    notes: Optional[str]

    version: int

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    items: List[QuotationItemOut]

class QuotationResponse(BaseModel):
    message: str
    data: QuotationOut

class QuotationListResponse(BaseModel):
    message: str
    total: int
    data: List[QuotationOut]
