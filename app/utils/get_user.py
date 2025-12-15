from fastapi import Depends, HTTPException, Header, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.users.user_models import User
from app.utils.logger import get_logger

logger = get_logger("auth.guard")


async def get_current_user(
    request: Request,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        logger.warning("Missing bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )

    token = authorization.split("Bearer ")[1].strip()
    payload = decode_access_token(token)

    username = payload.get("sub")
    token_version = payload.get("token_version")

    result = await db.execute(
        select(User).where(User.username == username)
    )
    user = result.scalars().first()

    if not user:
        logger.warning("Token user not found", extra={"username": username})
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        logger.warning("Inactive user access blocked", extra={"user_id": user.id})
        raise HTTPException(status_code=403, detail="User account is inactive")

    if user.token_version != token_version:
        logger.warning("Token version mismatch", extra={"user_id": user.id})
        raise HTTPException(status_code=401, detail="Session expired")

    request.state.user = user
    return user
