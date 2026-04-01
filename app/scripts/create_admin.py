"""
create_admin.py — One-time admin user creation script.

Usage:
    ADMIN_PASSWORD=<strong_password> python -m app.scripts.create_admin

ADMIN_PASSWORD must be set explicitly. There is no default — using a weak
default password for an admin account is a critical security risk (ERP-005).
"""

import asyncio
import os
import sys

from app.models.users.user_models import User
from app.core.db import AsyncSessionLocal
from app.core.security import hash_password


async def create_admin():
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        print(
            "ERROR: ADMIN_PASSWORD environment variable is not set.\n"
            "Set it before running this script:\n"
            "  ADMIN_PASSWORD=<strong_password> python -m app.scripts.create_admin",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(admin_password) < 12:
        print(
            "ERROR: ADMIN_PASSWORD must be at least 12 characters long.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        admin = User(
            username="admin@gmail.com",
            password_hash=hash_password(admin_password),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print("Admin user created successfully.")


asyncio.run(create_admin())
