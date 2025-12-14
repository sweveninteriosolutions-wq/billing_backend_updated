from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from app.models.enums.invoice_status import InvoiceStatus


class ORMBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str}
    )

class InvoiceItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class InvoiceCreate(BaseModel):
    customer_id: int
    quotation_id: Optional[int] = None
    items: List[InvoiceItemCreate]


class InvoiceDiscountApply(BaseModel):
    discount_amount: Decimal = Field(ge=0)
    reason: Optional[str] = None


class InvoicePaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_method: Optional[str] = None


class InvoiceItemOut(ORMBase):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class PaymentOut(ORMBase):
    id: int
    amount: Decimal
    payment_method: Optional[str]
    created_at: datetime


class InvoiceOut(ORMBase):
    id: int
    invoice_number: str
    customer_id: int
    quotation_id: Optional[int]
    status: InvoiceStatus

    gross_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    total_paid: Decimal
    balance_due: Decimal

    version: int
    created_at: datetime
    updated_at: Optional[datetime]

    items: List[InvoiceItemOut]
    payments: List[PaymentOut]


class InvoiceResponse(BaseModel):
    message: str
    data: InvoiceOut


class PaymentResponse(BaseModel):
    message: str
    data: PaymentOut


class ActionResponse(BaseModel):
    message: str


class InvoiceUpdate(BaseModel):
    version: int
    items: List[InvoiceItemCreate]


class InvoiceAdminDiscountOverride(BaseModel):
    version: int
    discount_amount: Decimal = Field(ge=0)
    reason: Optional[str] = None

class InvoiceListResponse(BaseModel):
    message: str
    total: int
    page: int
    page_size: int
    data: List[InvoiceOut]
