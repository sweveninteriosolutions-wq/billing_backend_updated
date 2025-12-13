# app/utils/get_user.py
from fastapi import Depends, HTTPException, Header, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.users.user_models import User

async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the currently authenticated user from an access token.

    - Supports `Authorization: Bearer <token>` OR `token: <token>`
    - Validates token version (global logout support)
    - Ensures user is active
    """

    # -----------------------------
    # Extract raw token
    # -----------------------------
    raw_token: str | None = None

    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split("Bearer ")[1].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token",
        )

    # -----------------------------
    # Decode & validate JWT
    # -----------------------------
    try:
        payload = decode_access_token(raw_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    username = payload.get("sub")
    token_version = payload.get("token_version")

    if not username or token_version is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # -----------------------------
    # Fetch user from DB
    # -----------------------------
    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # -----------------------------
    # Security checks
    # -----------------------------
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    if user.token_version != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )

    # -----------------------------
    # Attach user to request context
    # -----------------------------
    request.state.user = user
    return user
