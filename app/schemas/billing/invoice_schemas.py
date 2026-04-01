from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from decimal import Decimal
from datetime import datetime, date

from app.models.enums.invoice_status import InvoiceStatus


# =====================================================
# BASE
# =====================================================
class ORMBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str},
    )


# =====================================================
# ITEM INPUTS
# =====================================================
class InvoiceItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class InvoiceItemUpdate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


# =====================================================
# ITEM OUTPUT
# =====================================================
class InvoiceItemOut(ORMBase):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal


# =====================================================
# CREATE / UPDATE
# =====================================================
class InvoiceCreate(BaseModel):
    customer_id: int
    quotation_id: Optional[int] = None
    items: List[InvoiceItemCreate]
    is_inter_state: bool


class InvoiceUpdate(BaseModel):
    version: int
    items: List[InvoiceItemUpdate]


class InvoiceDiscountApply(BaseModel):
    discount_amount: Decimal = Field(ge=0)
    reason: Optional[str] = None


class InvoiceAdminDiscountOverride(BaseModel):
    version: int
    discount_amount: Decimal = Field(ge=0)
    reason: Optional[str] = None


class InvoicePaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_method: Optional[str] = None


# LOCK-P1-8 FIXED: Added version field to FulfillRequest so fulfill_invoice
# can perform an optimistic lock check. Without this, two concurrent requests
# could both fulfill the same invoice, each triggering inventory deductions
# and loyalty token grants for the same invoice — causing double-spend.
class InvoiceFulfillRequest(BaseModel):
    version: int


# =====================================================
# PAYMENT OUTPUT
# =====================================================
class PaymentOut(ORMBase):
    id: int
    amount: Decimal
    payment_method: Optional[str]
    created_at: datetime


# =====================================================
# SINGLE INVOICE OUTPUT
# ERP-031 FIXED: Added customer_snapshot field to InvoiceOut.
#   This field is stored on the invoice row at creation time and captures the
#   customer's name/email/phone at the point of sale — essential for audit trails
#   and for displaying correct customer info even if the customer record is later
#   updated or deactivated.
# =====================================================
class InvoiceOut(ORMBase):
    id: int
    invoice_number: str
    customer_id: int
    quotation_id: Optional[int]
    status: InvoiceStatus

    gross_amount: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal

    version: int

    created_at: datetime
    updated_at: Optional[datetime]

    # ERP-031 FIXED: Snapshot of customer data at time of invoice creation.
    # None for legacy invoices created before this field was added.
    customer_snapshot: Optional[dict[str, Any]] = None

    items: List[InvoiceItemOut]
    payments: List[PaymentOut]


# =====================================================
# LIST VIEW
# =====================================================
class InvoiceListItem(BaseModel):
    id: int
    invoice_number: str
    customer_name: str
    total_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal
    due_date: date | None
    status: InvoiceStatus


# =====================================================
# LIST RESPONSE DATA
# =====================================================
class InvoiceListData(BaseModel):
    total: int
    items: List[InvoiceListItem]
