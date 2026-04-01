# app/core/scheduler.py
# ERP-008 FIXED: All scheduler jobs now wrapped in try/except with structured logging.
# ERP-043 FIXED: Discount jobs run in isolated sessions so one failure doesn't corrupt the other.

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.db import AsyncSessionLocal

from app.services.billing.quotation_expiry_service import auto_expire_quotations
from app.services.masters.discount_expiry_n_activate_service import (
    auto_expire_discounts,
    auto_activate_discounts,
)

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


@scheduler.scheduled_job("cron", hour=0, minute=5)  # daily at 00:05
async def expire_quotations_job():
    """Auto-expire approved quotations whose valid_until date has passed."""
    try:
        async with AsyncSessionLocal() as db:
            count = await auto_expire_quotations(db)
            logger.info("expire_quotations_job complete", extra={"expired": count})
    except Exception:
        logger.exception("expire_quotations_job failed — will retry next scheduled run")


@scheduler.scheduled_job("cron", hour=0, minute=10)  # daily at 00:10
async def discount_expire_job():
    """Auto-expire active discounts whose end_date has passed."""
    # ERP-043: Isolated session so a failure here doesn't affect the activate job.
    try:
        async with AsyncSessionLocal() as db:
            count = await auto_expire_discounts(db)
            logger.info("discount_expire_job complete", extra={"expired": count})
    except Exception:
        logger.exception("discount_expire_job failed — will retry next scheduled run")


@scheduler.scheduled_job("cron", hour=0, minute=11)  # daily at 00:11 (after expiry)
async def discount_activate_job():
    """Auto-activate discounts whose start_date has arrived."""
    # ERP-043: Isolated session so expiry and activation are independent.
    try:
        async with AsyncSessionLocal() as db:
            count = await auto_activate_discounts(db)
            logger.info("discount_activate_job complete", extra={"activated": count})
    except Exception:
        logger.exception("discount_activate_job failed — will retry next scheduled run")
