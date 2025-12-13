from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# =========================
# REQUEST SCHEMAS
# =========================

class UserCreateSchema(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str


class UserUpdateSchema(BaseModel):
    """
    PATCH-style update.
    `version` is REQUIRED for optimistic locking.
    """
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    version: int


# =========================
# RESPONSE SCHEMAS
# =========================

class UserTableSchema(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    status: str
    last_login: Optional[datetime]
    is_online: bool
    version: int

    class Config:
        from_attributes = True


class UserResponseSchema(BaseModel):
    msg: str
    data: Optional[UserTableSchema] = None


class UsersListResponseSchema(BaseModel):
    msg: str
    data: List[UserTableSchema]


# =========================
# DASHBOARD
# =========================

class UserDashboardStatsSchema(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    online_users: int


class UserDashboardResponseSchema(BaseModel):
    msg: str
    data: UserDashboardStatsSchema
