from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.enums.stock_transfer_status import TransferStatus


# =====================================================
# BASE
# =====================================================
class StockTransferBase(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    from_location_id: int
    to_location_id: int


# =====================================================
# CREATE
# =====================================================
class StockTransferCreateSchema(StockTransferBase):
    pass


# =====================================================
# RESPONSE TABLE
# =====================================================
class StockTransferOutSchema(StockTransferBase):
    id: int
    status: TransferStatus
    transferred_by_id: int
    completed_by_id: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# =====================================================
# RESPONSE WRAPPERS
# =====================================================
class StockTransferResponse(BaseModel):
    message: str
    data: StockTransferOutSchema


class StockTransferListResponse(BaseModel):
    message: str
    total: int
    data: list[StockTransferOutSchema]
