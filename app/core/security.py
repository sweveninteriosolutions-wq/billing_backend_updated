from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from typing import Optional

from app.core.config import (
    JWT_ANON_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

# --------------------------------------------------
# Password hashing
# --------------------------------------------------

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --------------------------------------------------
# Access Token (JWT)
# --------------------------------------------------

def create_access_token(
    subject: str,
    token_version: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": subject,
        "token_version": token_version,
        "type": "access",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, JWT_ANON_SECRET, algorithm=JWT_ALGORITHM)


# --------------------------------------------------
# Decode + validate JWT
# --------------------------------------------------

def decode_access_token(token: str) -> dict:
    """
    Decode and validate an access token.
    Used ONLY by get_current_user.
    """
    try:
        payload = jwt.decode(token, JWT_ANON_SECRET, algorithms=[JWT_ALGORITHM])

        if payload.get("type") != "access":
            raise ValueError("Invalid token type")

        return payload

    except JWTError:
        raise ValueError("Invalid or expired token")
