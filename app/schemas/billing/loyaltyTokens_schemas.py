from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import List, Optional


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


# =========================
# REDEMPTION
# ERP-045: New schemas for loyalty token redemption
# =========================
class LoyaltyTokenRedeemRequest(BaseModel):
    customer_id: int
    tokens_to_redeem: int

    @field_validator("tokens_to_redeem")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("tokens_to_redeem must be a positive integer")
        return v


class LoyaltyTokenRedeemResponse(BaseModel):
    customer_id: int
    tokens_redeemed: int
    tokens_remaining: int
    redemption_id: int
