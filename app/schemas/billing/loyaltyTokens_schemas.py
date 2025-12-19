from pydantic import BaseModel
from datetime import datetime
from typing import List


# =========================
# OUT
# =========================
class LoyaltyTokenOut(BaseModel):
    id: int
    customer_id: int
    invoice_id: int
    tokens: int
    created_at: datetime

    model_config = {"from_attributes": True}


# =========================
# LIST DATA
# =========================
class LoyaltyTokenListData(BaseModel):
    total: int
    items: List[LoyaltyTokenOut]
