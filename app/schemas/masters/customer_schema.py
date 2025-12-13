# app/schemas/customer_schema.py
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime


class CustomerBase(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[Dict[str, str]] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    email: Optional[EmailStr] = None

    version: int


class CustomerOut(CustomerBase):
    id: int
    is_active: bool
    version: int

    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    created_at: datetime

    class Config:
        from_attributes = True


class CustomerResponse(BaseModel):
    message: str
    data: Optional[CustomerOut] = None


class CustomerListResponse(BaseModel):
    message: str
    total: int
    data: List[CustomerOut]