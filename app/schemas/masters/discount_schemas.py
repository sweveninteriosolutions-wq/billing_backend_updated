from pydantic import BaseModel, Field, computed_field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


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


class DiscountOut(DiscountBase):
    id: int
    used_count: int
    is_active: bool
    is_deleted: bool
    created_at: datetime

    @computed_field
    def status(self) -> str:
        if self.is_deleted:
            return "deleted"
        return "active" if self.is_active else "inactive"

    class Config:
        from_attributes = True


class DiscountResponse(BaseModel):
    message: str
    data: DiscountOut


class DiscountListResponse(BaseModel):
    message: str
    total: int
    data: list[DiscountOut]
