# app/core/scheduler.py
# ERP-008 FIXED: All scheduler jobs now wrapped in try/except with structured logging.
# ERP-043 FIXED: Discount jobs run in isolated sessions so one failure doesn't corrupt the other.
# SEC-P0-3 FIXED: Scheduler is designed to run in a DEDICATED process (app/core/run_scheduler.py),
#   NOT inside every Gunicorn worker. In multi-worker deployments, starting the scheduler inside
#   the API lifespan causes every worker to execute cron jobs independently, resulting in duplicate
#   DB writes (double-expiry, double-activation). The main.py lifespan still starts the scheduler
#   in development (single process), but production must use run_scheduler.py as a separate container.
# SEC-P1-3 FIXED: Added purge_expired_refresh_tokens_job to prevent unbounded table growth.

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, or_, and_

from app.core.db import AsyncSessionLocal
from app.models.users.user_models import RefreshToken

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


@scheduler.scheduled_job("cron", hour=2, minute=0)  # daily at 02:00
async def purge_expired_refresh_tokens_job():
    """
    SEC-P1-3 FIXED: Delete refresh tokens that are either:
      - expired (expires_at older than RETENTION_DAYS ago), or
      - revoked AND created more than RETENTION_DAYS ago.
    Without this job, the refresh_tokens table grows unboundedly with every login.
    """
    RETENTION_DAYS = 30
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(RefreshToken).where(
                    or_(
                        RefreshToken.expires_at < cutoff,
                        and_(
                            RefreshToken.revoked.is_(True),
                            RefreshToken.created_at < cutoff,
                        ),
                    )
                )
            )
            await db.commit()
            logger.info(
                "purge_expired_refresh_tokens_job complete",
                extra={"deleted": result.rowcount},
            )
    except Exception:
        logger.exception("purge_expired_refresh_tokens_job failed — will retry next scheduled run")
