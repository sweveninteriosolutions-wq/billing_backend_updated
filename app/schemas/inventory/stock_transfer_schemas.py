from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from app.models.enums.stock_transfer_status import TransferStatus


class StockTransferCreateSchema(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    from_location_id: int
    to_location_id: int


class StockTransferTableSchema(BaseModel):
    id: int
    product_id: int
    quantity: int
    from_location_id: int
    to_location_id: int
    status: TransferStatus

    transferred_by_id: int
    transferred_by: Optional[str]

    completed_by_id: Optional[int]
    completed_by: Optional[str]

    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class StockTransferResponse(BaseModel):
    message: str
    data: StockTransferTableSchema


class StockTransferListResponse(BaseModel):
    message: str
    total: int
    data: List[StockTransferTableSchema]
