from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL, DB_TYPE
import ssl

Base = declarative_base()

# Build connect_args safely based on DB type
if DB_TYPE == "postgres":
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "server_settings": {"prepareThreshold": "0"},
        "ssl": ssl_ctx,
    }

    pool_args = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_pre_ping": True,
    }

else:
    # SQLite
    connect_args = {"check_same_thread": False}
    pool_args = {}

# Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
    echo_pool=True,   # 🔥 ADD THIS
    **pool_args,
)

# Session factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# DB dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Foreign key enforcement for SQLite
if DB_TYPE == "sqlite":
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

import app.models

# Create tables automatically (for dev)
async def init_models():
    import os
    # This should only be run in a development environment.
    # In production, you should use a migration tool like Alembic.
    if os.getenv("APP_ENV", "production") == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
