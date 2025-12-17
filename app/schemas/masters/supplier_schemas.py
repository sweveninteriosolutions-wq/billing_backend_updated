from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class SupplierBase(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None

    version: int


class SupplierOut(SupplierBase):
    id: int
    supplier_code: str
    is_active: bool
    version: int

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True


class SupplierListData(BaseModel):
    total: int
    items: List[SupplierOut]
