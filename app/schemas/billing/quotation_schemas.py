from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, date

from app.models.enums.quotation_status import QuotationStatus

# =====================================================
# ITEM PAYLOADS (CREATE / UPDATE)
# =====================================================

class QuotationItemCreate(BaseModel):
    product_id: int
    quantity: int


class QuotationItemUpdate(BaseModel):
    product_id: int
    quantity: int


# =====================================================
# ITEM RESPONSES
# =====================================================

class QuotationItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    hsn_code: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class QuotationItemDetailOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    sku: Optional[str]
    hsn_code: int
    category: Optional[str]
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class QuotationItemViewOut(BaseModel):
    id: int
    quotation_id: int
    product_id: int
    product_name: str
    hsn_code: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    created_by_id: Optional[int]
    created_by_name: Optional[str]

    class Config:
        from_attributes = True


# =====================================================
# QUOTATION CREATE / UPDATE
# =====================================================

class QuotationCreate(BaseModel):
    customer_id: int
    is_inter_state: bool
    items: List[QuotationItemCreate]
    valid_until: date
    description: Optional[str] = None
    notes: Optional[str] = None


class QuotationUpdate(BaseModel):
    is_inter_state: Optional[bool] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    valid_until: Optional[date] = None
    items: Optional[List[QuotationItemUpdate]] = None
    version: int


# =====================================================
# QUOTATION BASIC RESPONSE
# =====================================================

class QuotationOut(BaseModel):
    id: int
    quotation_number: str
    customer_id: int
    status: QuotationStatus

    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    valid_until: Optional[date]
    description: Optional[str]
    notes: Optional[str]

    version: int

    created_by_id: Optional[int]
    updated_by_id: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    items: List[QuotationItemOut]


# =====================================================
# QUOTATION LIST RESPONSE
# =====================================================

class QuotationListItem(BaseModel):
    id: int
    quotation_number: str
    customer_id: int
    customer_name: str

    status: QuotationStatus
    items_count: int

    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    valid_until: Optional[date]
    version: int
    is_deleted: bool

    created_at: datetime
    created_by_name: Optional[str]


class QuotationListData(BaseModel):
    total: int
    items: List[QuotationListItem]


# =====================================================
# QUOTATION DETAIL VIEW (ERP VIEW)
# =====================================================

class CustomerOut(BaseModel):
    id: int
    customer_code: str
    name: str
    email: str
    phone: Optional[str]
    gstin: Optional[str]
    address: Optional[dict]
    is_active: bool


class QuotationDetailViewOut(BaseModel):
    id: int
    quotation_number: str

    customer: CustomerOut

    status: QuotationStatus
    valid_until: Optional[date]

    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal

    is_inter_state: bool

    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal

    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal

    description: Optional[str]
    notes: Optional[str]
    additional_data: Optional[dict]

    item_signature: Optional[str]
    version: int

    created_at: datetime
    updated_at: Optional[datetime]

    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    items: List[QuotationItemDetailOut]

    class Config:
        from_attributes = True
