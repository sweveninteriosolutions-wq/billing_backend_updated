# app/core/security.py

from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, status

from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# =====================================================
# PASSWORD HASHING
# =====================================================
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# =====================================================
# ACCESS TOKEN
# =====================================================
def create_access_token(
    subject: str,
    token_version: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": subject,
        "token_version": token_version,
        "type": "access",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

# =====================================================
# DECODE + VALIDATE TOKEN
# =====================================================
def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
