from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class InventoryLocationCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)


class InventoryLocationUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    name: Optional[str] = None
    version: int


class InventoryLocationOut(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    version: int

    created_at: datetime
    updated_at: Optional[datetime]

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    class Config:
        from_attributes = True


class InventoryLocationListData(BaseModel):
    total: int
    items: List[InventoryLocationOut]
