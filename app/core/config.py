import os
from dotenv import load_dotenv

load_dotenv()

# -----------------------
# Database Config
# -----------------------
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()

if DB_TYPE == "postgres":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is required for Postgres setup")
elif DB_TYPE == "sqlite":
    DATABASE_URL = "sqlite+aiosqlite:///./test.db"
else:
    raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}")

# -----------------------
# JWT Config
# -----------------------
JWT_ANON_SECRET = os.getenv("JWT_ANON_SECRET")
if not JWT_ANON_SECRET:
    raise ValueError("JWT_ANON_SECRET environment variable must be set")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7
