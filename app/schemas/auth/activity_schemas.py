from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserActivityOut(BaseModel):
    id: int
    user_id: Optional[int]
    username_snapshot: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserActivityListResponse(BaseModel):
    message: str
    total: int
    data: List[UserActivityOut]