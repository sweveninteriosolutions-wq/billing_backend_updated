from pydantic import BaseModel, EmailStr
from typing import Optional, Literal



class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str]
    token_type: Literal["bearer"] = "bearer"
    role: str


class MessageResponse(BaseModel):
    msg: str
