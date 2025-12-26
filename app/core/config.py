# app/core/config.py

import os
from dotenv import load_dotenv
from app.utils.logger import get_logger

logger = get_logger(__name__)

load_dotenv()

# =====================================================
# APPLICATION
# =====================================================
APP_ENV = os.getenv("APP_ENV")
if APP_ENV not in {"development", "staging", "production"}:
    raise ValueError("APP_ENV must be development | staging | production")

IS_PRODUCTION = APP_ENV == "production"

# =====================================================
# DATABASE
# =====================================================
DB_TYPE = os.getenv("DB_TYPE")
if DB_TYPE not in {"postgres", "sqlite"}:
    raise ValueError("DB_TYPE must be postgres | sqlite")

if DB_TYPE == "postgres":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is required for Postgres")

elif DB_TYPE == "sqlite":
    if IS_PRODUCTION:
        raise ValueError("SQLite is NOT allowed in production")
    DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# ---- Pool tuning (safe defaults) ----
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 10))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", 20))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", 30))
DB_ECHO_POOL = os.getenv("DB_ECHO_POOL", "false").lower() == "true"

# ---- SSL ----
# MUST be true in production
DB_SSL_VERIFY = os.getenv("DB_SSL_VERIFY", "true").lower() == "true"
# Supabase + asyncpg requires relaxed cert verification
if IS_PRODUCTION:
    logger.warning(
        "Running in production with relaxed SSL verification "
        "(Supabase asyncpg compatibility mode)"
    )

# =====================================================
# JWT / AUTH
# =====================================================
JWT_ACCESS_SECRET_KEY = os.getenv("JWT_ACCESS_SECRET_KEY")
if not JWT_ACCESS_SECRET_KEY:
    raise ValueError("JWT_ACCESS_SECRET_KEY must be set")

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15)
)
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES", 60)
)
REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7)
)
