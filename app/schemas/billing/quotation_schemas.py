from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date


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


class QuotationCreate(BaseModel):
    customer_id: int
    is_inter_state: bool
    items: List[QuotationItemCreate]
    valid_until: date
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


class QuotationListItem(BaseModel):
    id: int
    quotation_number: str
    customer_name: str
    status: str
    items_count: int
    total_amount: Decimal
    valid_until: Optional[date]


class QuotationListData(BaseModel):
    total: int
    items: List[QuotationListItem]

