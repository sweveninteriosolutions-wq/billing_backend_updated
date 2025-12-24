from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.users.user_models import User, RefreshToken
from app.core.security import verify_password, create_access_token
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode
from app.utils.logger import get_logger

logger = get_logger("auth.service")


# =====================================================
# LOGIN
# =====================================================
async def login_user(db: AsyncSession, email: str, password: str):
    logger.info("Authenticating user", extra={"email": email})

    result = await db.execute(
        select(User).where(User.username == email)
    )
    user = result.scalars().first()

    if not user or not verify_password(password, user.password_hash):
        logger.warning("Invalid credentials", extra={"email": email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        logger.warning("Inactive user login blocked", extra={"email": email})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    user.last_login = datetime.now(timezone.utc)
    user.is_online = True

    access_token = create_access_token(
        subject=user.username,
        token_version=user.token_version,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_value = secrets.token_urlsafe(48)
    refresh_expiry = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_value,
            expires_at=refresh_expiry,
        )
    )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.LOGIN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
    )

    await db.commit()

    logger.info("Login successful", extra={"user_id": user.id})

    return {
            "auth": {
                "access_token": access_token,
                "refresh_token": refresh_value,
                "token_type": "bearer",
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
            },
    }



# =====================================================
# REFRESH
# =====================================================
async def refresh_tokens(db: AsyncSession, refresh_token_value: str):
    logger.info("Refreshing token")

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token_value,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    token = result.scalars().first()

    if not token:
        logger.warning("Invalid refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await db.get(User, token.user_id)
    if not user or not user.is_active:
        logger.warning("Refresh blocked for inactive user", extra={"user_id": token.user_id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User invalid or inactive",
        )

    token.revoked = True

    new_refresh_value = secrets.token_urlsafe(48)
    new_refresh_expiry = datetime.now(timezone.utc) + timedelta(
        days=REFRESH_TOKEN_EXPIRE_DAYS
    )

    db.add(
        RefreshToken(
            user_id=user.id,
            token=new_refresh_value,
            expires_at=new_refresh_expiry,
        )
    )

    access_token = create_access_token(
        subject=user.username,
        token_version=user.token_version,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    await db.commit()

    logger.info("Token refreshed", extra={"user_id": user.id})

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_value,
        "token_type": "bearer",
        "role": user.role,
    }


# =====================================================
# LOGOUT
# =====================================================
async def logout_user(db: AsyncSession, user: User):
    logger.info("Logging out user", extra={"user_id": user.id})

    user.token_version += 1
    user.is_online = False

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .values(revoked=True)
    )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.LOGOUT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
    )

    await db.commit()

    logger.info("Logout successful", extra={"user_id": user.id})
