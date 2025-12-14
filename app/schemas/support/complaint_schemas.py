from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.models.support.complaint_models import (
    ComplaintStatus,
    ComplaintPriority,
)


class ComplaintBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: ComplaintPriority = ComplaintPriority.MEDIUM


class ComplaintCreate(ComplaintBase):
    customer_id: int
    invoice_id: Optional[int] = None
    product_id: Optional[int] = None


class ComplaintUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[ComplaintPriority] = None


class ComplaintStatusUpdate(BaseModel):
    status: ComplaintStatus


class ComplaintOut(ComplaintBase):
    id: int
    customer_id: int
    invoice_id: Optional[int]
    product_id: Optional[int]
    status: ComplaintStatus
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ComplaintResponse(BaseModel):
    message: str
    data: ComplaintOut


class ComplaintListResponse(BaseModel):
    message: str
    total: int
    data: list[ComplaintOut]
