# app/core/config.py

import os
from decimal import Decimal
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
DB_SSL_VERIFY = os.getenv("DB_SSL_VERIFY", "true").lower() == "true"
if IS_PRODUCTION and not DB_SSL_VERIFY:
    logger.warning(
        "SECURITY WARNING: DB_SSL_VERIFY=false in production. "
        "This will be rejected at engine startup."
    )

# =====================================================
# JWT / AUTH
# SEC-P0-1 FIXED: Added guards against weak or misconfigured JWT secrets.
# Previously only checked for empty string. Now enforces:
#   1. Minimum length of 32 characters (256-bit for HS256).
#   2. Rejects the Supabase anon/service key pattern — this key is PUBLIC
#      and must never be used as an HMAC signing secret.
# Generate a proper secret: python -c "import secrets; print(secrets.token_hex(64))"
# =====================================================
JWT_ACCESS_SECRET_KEY = os.getenv("JWT_ACCESS_SECRET_KEY")
if not JWT_ACCESS_SECRET_KEY:
    raise ValueError("JWT_ACCESS_SECRET_KEY must be set")

if len(JWT_ACCESS_SECRET_KEY) < 32:
    raise ValueError(
        "SECURITY ERROR (SEC-P0-1): JWT_ACCESS_SECRET_KEY is too short. "
        "Minimum 32 characters required for HS256. "
        "Generate with: python -c \"import secrets; print(secrets.token_hex(64))\""
    )

# Detect Supabase anon/service key pattern (base64 JWT with 3 segments).
# These are PUBLIC keys and must NEVER be used as HMAC secrets.
_jwt_parts = JWT_ACCESS_SECRET_KEY.split(".")
if len(_jwt_parts) == 3:
    raise ValueError(
        "SECURITY ERROR (SEC-P0-1): JWT_ACCESS_SECRET_KEY appears to be a Supabase "
        "anon/service key (3-segment JWT). This key is PUBLIC and cannot be used as "
        "an HMAC signing secret — anyone can forge tokens with it. "
        "Generate a proper secret: python -c \"import secrets; print(secrets.token_hex(64))\""
    )

JWT_ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# =====================================================
# INVENTORY / WAREHOUSE
# =====================================================
DEFAULT_WAREHOUSE_LOCATION_ID = int(os.getenv("DEFAULT_WAREHOUSE_LOCATION_ID", 1))

# =====================================================
# GST — ERP-032/033/034/052 FIXED
# Single source of truth for GST rate across all services.
# Previously: each service called os.getenv("GST_RATE") independently,
#             and GST_RATE_ENV in config.py was read but never used.
# Now:        all services import GST_RATE from here.
# =====================================================
_gst_rate_str = os.getenv("GST_RATE", "0.18")
try:
    GST_RATE = Decimal(_gst_rate_str)
except Exception:
    raise ValueError(f"GST_RATE must be a valid decimal number, got: '{_gst_rate_str}'")

# =====================================================
# FILE UPLOADS
# =====================================================
UPLOAD_BASE_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", 10))
ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}

# =====================================================
# COMPANY BRANDING (for PDF generation)
# ERP-030 FIXED: invoice_pdf.py now imports these instead of reading os.getenv() directly.
# =====================================================
COMPANY_NAME = os.getenv("COMPANY_NAME", "Varasidhi Furnitures")
COMPANY_GSTIN = os.getenv("COMPANY_GSTIN", "29XXXXX0000X1Z5")
COMPANY_ADDRESS_LINE1 = os.getenv("COMPANY_ADDRESS_LINE1", "No. 1, Main Road")
COMPANY_ADDRESS_LINE2 = os.getenv("COMPANY_ADDRESS_LINE2", "Bengaluru, Karnataka - 560001")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "+91 98765 43210")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "billing@varasidhi.com")
