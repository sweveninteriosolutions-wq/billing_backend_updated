# tests/conftest.py
#
# Shared test infrastructure for all Sweven service tests.
#
# DB: SQLite + aiosqlite in-memory — fast, isolated, no external deps.
# Session: each test gets its own SAVEPOINT that is ROLLED BACK after the test,
#          so no rows ever persist between tests.
# User stub: a lightweight object that mimics the User model for service calls
#            without needing a real ORM-loaded row.

import os
import pytest
import pytest_asyncio

# -----------------------------------------------------------------------
# Set env vars BEFORE any app module is imported.
# config.py validates these at import time — must be set first.
# -----------------------------------------------------------------------
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DB_TYPE", "sqlite")
os.environ.setdefault("JWT_ACCESS_SECRET_KEY", "TestSecretKeyThatIsAtLeast32CharsLongXXX")
os.environ.setdefault("GST_RATE", "0.18")
os.environ.setdefault("DEFAULT_WAREHOUSE_LOCATION_ID", "1")

import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import event

from app.core.db import Base
import app.models  # registers ALL models with Base.metadata  # noqa

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# -----------------------------------------------------------------------
# Event loop — session-scoped.
# -----------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# -----------------------------------------------------------------------
# Engine — created once for the entire test run.
# -----------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


# -----------------------------------------------------------------------
# Per-test DB session — rolls back after every test via SAVEPOINT.
# -----------------------------------------------------------------------
@pytest_asyncio.fixture()
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    async with engine.connect() as conn:
        await conn.begin()
        await conn.begin_nested()  # SAVEPOINT

        session = AsyncSession(
            bind=conn,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# -----------------------------------------------------------------------
# StubUser — passed wherever services expect a `user` argument.
# -----------------------------------------------------------------------
class StubUser:
    def __init__(
        self,
        id: int = 1,
        username: str = "admin@test.com",
        role: str = "admin",
        is_active: bool = True,
        version: int = 1,
    ):
        self.id = id
        self.username = username
        self.role = role
        self.is_active = is_active
        self.version = version


@pytest.fixture()
def admin_user() -> StubUser:
    return StubUser(id=1, username="admin@test.com", role="admin")


@pytest.fixture()
def cashier_user() -> StubUser:
    return StubUser(id=2, username="cashier@test.com", role="cashier")


# -----------------------------------------------------------------------
# _seed_user — inserts a real User row to satisfy FK constraints.
# Called inside async fixtures/tests that need it.
# -----------------------------------------------------------------------
from app.models.users.user_models import User
from app.core.security import hash_password


async def seed_user(
    db: AsyncSession,
    *,
    id: int = 1,
    username: str = "admin@test.com",
    role: str = "admin",
) -> User:
    user = User(
        id=id,
        username=username,
        password_hash=hash_password("TestPassword1!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user
