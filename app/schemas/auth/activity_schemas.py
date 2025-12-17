# app/schemas/auth/activity_schemas.py

from pydantic import BaseModel
from typing import Optional
from fastapi import Query


class UserActivityFilters(BaseModel):
    user_id: Optional[int] = Query(None)
    username: Optional[str] = Query(None)

    page: int = Query(1, ge=1)
    page_size: int = Query(20, ge=1, le=100)

    sort_by: str = Query("created_at")
    sort_order: str = Query("desc")


# app/schemas/auth/activity_schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserActivityOut(BaseModel):
    id: int
    user_id: Optional[int]
    username_snapshot: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
