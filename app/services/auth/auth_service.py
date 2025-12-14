from datetime import timedelta, datetime, timezone
import secrets

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.users.user_models import User, RefreshToken
from app.core.security import verify_password, create_access_token
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode


# =====================================================
# LOGIN
# =====================================================
async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
):
    result = await db.execute(
        select(User).where(User.username == email)
    )
    user = result.scalars().first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    # -------------------------------------------------
    # Update user session state
    # -------------------------------------------------
    user.last_login = datetime.now(timezone.utc)
    user.is_online = True

    # -------------------------------------------------
    # Tokens
    # -------------------------------------------------
    access_token = create_access_token(
        subject=user.username,
        token_version=user.token_version,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_value = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=refresh_value,
        )
    )

    # -------------------------------------------------
    # Activity (NO COMMIT HERE)
    # -------------------------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.LOGIN,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
    )

    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_value,
        "token_type": "bearer",
        "role": user.role,
    }


# =====================================================
# REFRESH TOKENS
# =====================================================
async def refresh_tokens(
    db: AsyncSession,
    refresh_token_value: str,
):
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token_value,
            RefreshToken.revoked.is_(False),
        )
    )
    token = result.scalars().first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await db.get(User, token.user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User invalid or inactive",
        )

    # -------------------------------------------------
    # Revoke old token
    # -------------------------------------------------
    token.revoked = True

    # -------------------------------------------------
    # Issue new refresh token
    # -------------------------------------------------
    new_refresh_value = secrets.token_urlsafe(48)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=new_refresh_value,
        )
    )

    # -------------------------------------------------
    # New access token
    # -------------------------------------------------
    access_token = create_access_token(
        subject=user.username,
        token_version=user.token_version,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_value,
        "token_type": "bearer",
        "role": user.role,
    }


# =====================================================
# LOGOUT
# =====================================================
async def logout_user(
    db: AsyncSession,
    user: User,
):
    # -------------------------------------------------
    # Invalidate all tokens
    # -------------------------------------------------
    user.token_version += 1
    user.is_online = False

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .values(revoked=True)
    )

    # -------------------------------------------------
    # Activity (NO COMMIT HERE)
    # -------------------------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.LOGOUT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
    )

    await db.commit()
