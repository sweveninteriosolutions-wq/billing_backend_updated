from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# =========================
# BASE RESPONSE
# =========================
class APIResponse(BaseModel):
    success: bool = True
    message: str
    data: Optional[object] = None


# =========================
# CREATE / UPDATE
# =========================
class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str


class UserUpdateSchema(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    version: int


class VersionOnlySchema(BaseModel):
    version: int


# =========================
# LIST FILTERS
# =========================
class UserListFilters(BaseModel):
    search: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_online: Optional[bool] = None
    created_today: Optional[bool] = None
    created_by: Optional[int] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    limit: int = 50
    offset: int = 0


# =========================
# RESPONSE SCHEMAS
# =========================
class UserListItemSchema(BaseModel):
    id: int
    username: EmailStr
    role: str
    status: str
    is_online: bool
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserDetailSchema(BaseModel):
    id: int
    username: EmailStr
    role: str
    is_active: bool
    is_online: bool
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    created_by_admin_id: Optional[int]
    version: int

    class Config:
        from_attributes = True


# =========================
# DASHBOARD
# =========================
class UserDashboardStatsSchema(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    online_users: int
