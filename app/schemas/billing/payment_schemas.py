from pydantic import BaseModel
from datetime import datetime, date
from decimal import Decimal
from typing import Optional


# =====================================================
# OUT
# =====================================================
class PaymentOut(BaseModel):
    id: int
    invoice_id: int
    amount: Decimal
    payment_method: Optional[str]
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
# =====================================================
# RESPONSE WRAPPERS
# =====================================================
class PaymentResponse(BaseModel):
    message: str
    data: PaymentOut


class PaymentListResponse(BaseModel):
    message: str
    total: int
    data: list[PaymentOut]
