from app.models.users.user_models import User
from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
import asyncio
import os

async def create_admin():
    async with AsyncSessionLocal() as session:
        admin = User(
            username="admin@gmail.com",
            password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "admin123")),
            role="admin",
            is_active=True
        )
        session.add(admin)
        await session.commit()
        print("Admin user created!")

asyncio.run(create_admin())
