from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime


from typing import Generic, Optional, TypeVar
from pydantic.generics import GenericModel

T = TypeVar("T")


class APIResponse(GenericModel, Generic[T]):
    success: bool = True
    message: str
    data: Optional[T] = None



# =========================
# CREATE / UPDATE
# =========================
class UserCreateSchema(BaseModel):
    email: EmailStr
    # SEC-P2-2 FIXED: Increased minimum password length from 6 to 10 and added
    # complexity requirements. 6-char passwords are trivially brute-forceable even
    # with bcrypt — the cost factor slows each attempt but doesn't stop offline attacks.
    password: str = Field(
        min_length=10,
        description="Minimum 10 characters; must contain at least one uppercase letter and one digit",
    )
    role: str

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdateSchema(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=10)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    version: int


class VersionOnlySchema(BaseModel):
    version: int


# =========================
# LIST FILTERS
# =========================
VALID_SORT_FIELDS = {"created_at", "username"}
VALID_SORT_ORDERS = {"asc", "desc"}

class UserListFilters(BaseModel):
    search: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    is_online: Optional[bool] = None
    created_today: Optional[bool] = None
    created_by: Optional[int] = None
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc")
    page: int = Field(default=1, ge=1)
    # SEC-P1-9 FIXED: Added upper bound to page_size.
    # Without le=100, a caller can request page_size=999999 causing a full table
    # scan and potential OOM on large datasets.
    page_size: int = Field(default=10, ge=1, le=100)

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        # SEC-P2-4 FIXED: Reject unknown sort_order values.
        # Previously any string was accepted; the service-layer sort_map handled
        # unknown sort_by values but sort_order was lowercased and passed directly
        # into .asc()/.desc() — unexpected values silently defaulted to asc.
        if v.lower() not in VALID_SORT_ORDERS:
            raise ValueError(f"sort_order must be one of: {VALID_SORT_ORDERS}")
        return v.lower()

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        if v not in VALID_SORT_FIELDS:
            raise ValueError(f"sort_by must be one of: {VALID_SORT_FIELDS}")
        return v


# =========================
# RESPONSE SCHEMAS
# =========================
class UserListItemSchema(BaseModel):
    id: int
    username: EmailStr
    role: str
    is_active: bool
    is_online: bool
    last_login: Optional[datetime]
    version: int

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

class UserListResponseSchema(BaseModel):
    items: List[UserListItemSchema]
    total: int
    page: int
    page_size: int
