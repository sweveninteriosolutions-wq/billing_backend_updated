# app/core/db.py

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event

from app.core.config import (
    DATABASE_URL,
    DB_TYPE,
    DB_POOL_SIZE,
    DB_MAX_OVERFLOW,
    DB_POOL_TIMEOUT,
    DB_ECHO_POOL,
    APP_ENV,
    IS_PRODUCTION,
)

# =====================================================
# BASE
# =====================================================
Base = declarative_base()

# =====================================================
# CONNECTION CONFIG
# =====================================================
connect_args = {}
pool_args = {}

if DB_TYPE == "postgres":

    # 🔥 ENV-AWARE SSL HANDLING (THIS IS THE REAL FIX)
    if IS_PRODUCTION:
        # Production (Render / cloud)
        connect_args = {
            "ssl": True,
            "statement_cache_size": 0,
        }
    else:
        # Local development (avoid SSL cert issues)
        connect_args = {
            "ssl": False,
            "statement_cache_size": 0,
        }

    pool_args = {
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_pre_ping": True,
    }

elif DB_TYPE == "sqlite":
    connect_args = {"check_same_thread": False}

# =====================================================
# ENGINE
# =====================================================
engine = create_async_engine(
    DATABASE_URL,
    echo=False,                 # NEVER enable in prod
    echo_pool=DB_ECHO_POOL,     # debugging only
    future=True,
    connect_args=connect_args,
    **pool_args,
)

# =====================================================
# SESSION
# =====================================================
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# =====================================================
# DEPENDENCY
# =====================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

# =====================================================
# SQLITE FK ENFORCEMENT
# =====================================================
if DB_TYPE == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# =====================================================
# MODEL IMPORT
# =====================================================
import app.models  # noqa

# =====================================================
# DEV ONLY: AUTO CREATE TABLES
# =====================================================
async def init_models():
    if APP_ENV != "development":
        raise RuntimeError("init_models() is forbidden outside development")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)