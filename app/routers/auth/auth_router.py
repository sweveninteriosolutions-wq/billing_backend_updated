from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.auth.auth_schemas import (
    LoginRequest,
    RefreshRequest,
)
from app.services.auth.auth_service import (
    login_user,
    refresh_tokens,
    logout_user,
)
from app.utils.get_user import get_current_user
from app.utils.logger import get_logger

logger = get_logger("auth.router")

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    logger.info("Login attempt", extra={"email": payload.email})

    tokens = await login_user(db, payload.email, payload.password)

    return {
        "success": True,
        "message": "Login successful",
        "data": tokens,
    }


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    logger.info("Token refresh attempt")

    tokens = await refresh_tokens(db, payload.refresh_token)

    return {
        "success": True,
        "message": "Token refreshed",
        "data": tokens,
    }


@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(
        "Logout request",
        extra={"user_id": current_user.id, "email": current_user.username},
    )

    await logout_user(db, current_user)

    return {
        "success": True,
        "message": "Logged out successfully",
        "data": None,
    }
