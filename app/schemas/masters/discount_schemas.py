# app/schemas/masters/discount_schemas.py

from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List


class DiscountBase(BaseModel):
    name: str
    code: str
    discount_type: str = Field(..., pattern="^(percentage|flat)$")
    discount_value: Decimal
    start_date: date
    end_date: date
    usage_limit: Optional[int] = None
    note: Optional[str] = None


class DiscountCreate(DiscountBase):
    pass


class DiscountUpdate(BaseModel):
    name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    usage_limit: Optional[int] = None
    note: Optional[str] = None
    is_active: Optional[bool] = None

    version: int


class DiscountOut(BaseModel):
    id: int
    name: str
    code: str
    discount_type: str
    discount_value: Decimal

    is_active: bool
    is_deleted: bool

    start_date: date
    end_date: date
    usage_limit: Optional[int]
    used_count: int
    note: Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    class Config:
        from_attributes = True



class DiscountListData(BaseModel):
    total: int
    items: List[DiscountOut]

class VersionPayload(BaseModel):
    version: int