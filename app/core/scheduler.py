from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.db import AsyncSessionLocal

from app.services.billing.quotation_expiry_service import auto_expire_quotations

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("cron", hour=0, minute=5)  # daily at 00:05
async def expire_quotations_job():
    async with AsyncSessionLocal() as db:
        await auto_expire_quotations(db)
