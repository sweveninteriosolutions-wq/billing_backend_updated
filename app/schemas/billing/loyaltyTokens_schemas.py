from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
from typing import List


class LoyaltyTokenOut(BaseModel):
    id: int
    customer_id: int
    invoice_id: int
    tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


class LoyaltyTokenResponse(BaseModel):
    message: str
    data: LoyaltyTokenOut


class LoyaltyTokenListResponse(BaseModel):
    message: str
    total: int
    data: List[LoyaltyTokenOut]
