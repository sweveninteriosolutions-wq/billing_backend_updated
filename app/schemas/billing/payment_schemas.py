from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from typing import Optional, List


# =========================
# OUT
# =========================
class PaymentOut(BaseModel):
    id: int
    invoice_id: int
    amount: Decimal
    payment_method: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# =========================
# LIST DATA
# =========================
class PaymentListData(BaseModel):
    total: int
    items: List[PaymentOut]
