from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.auth.auth_schemas import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    MessageResponse,
)
from app.services.auth.auth_service import (
    login_user,
    refresh_tokens,
    logout_user,
)
from app.utils.get_user import get_current_user


router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    return await login_user(db, payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    return await refresh_tokens(db, payload.refresh_token)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def logout(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    await logout_user(db, current_user)
    return {"msg": "Logged out successfully"}

