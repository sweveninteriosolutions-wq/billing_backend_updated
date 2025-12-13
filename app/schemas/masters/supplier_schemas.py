from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class SupplierCreateSchema(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None


class SupplierUpdateSchema(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    is_active: Optional[bool] = None
    version: int


class SupplierTableSchema(BaseModel):
    id: int
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None

    is_active: bool
    version: int

    created_at: datetime
    updated_at: datetime | None

    created_by_id: int | None
    updated_by_id: int | None
    created_by_name: str | None
    updated_by_name: str | None

    class Config:
        from_attributes = True



class SupplierResponseSchema(BaseModel):
    msg: str
    data: Optional[SupplierTableSchema] = None


class SupplierListResponseSchema(BaseModel):
    msg: str
    total: int
    data: List[SupplierTableSchema]

class VersionPayload(BaseModel):
    version: int