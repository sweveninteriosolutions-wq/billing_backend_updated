# app/core/run_scheduler.py
"""
SEC-P0-3 FIX: Standalone scheduler process.

PROBLEM: Starting APScheduler inside the FastAPI lifespan means every Gunicorn
worker runs every cron job. With 2 workers, each job fires TWICE per schedule.
With N workers: N times. This causes double-expiry, double-activation, etc.

SOLUTION: Run the scheduler as a SEPARATE container / process with a single
instance. The API containers never start the scheduler.

Usage:
    python -m app.core.run_scheduler

Docker Compose:
    services:
      api:
        command: gunicorn main:app --workers 4 ...
        environment:
          ENABLE_SCHEDULER: "false"  # MUST be false on API containers
      scheduler:
        command: python -m app.core.run_scheduler
        deploy:
          replicas: 1              # MUST be exactly 1 — never scale this service

Production note:
    If you cannot run a separate container, set ENABLE_SCHEDULER=true on EXACTLY
    ONE worker by using gunicorn --workers 1 for the scheduler worker and routing
    cron traffic there. Do NOT set ENABLE_SCHEDULER=true on multi-worker deployments.
"""

import asyncio
import logging
import signal
import sys

from app.core.logging import setup_logging
from app.core.scheduler import scheduler

setup_logging()
logger = logging.getLogger("scheduler.runner")


async def main():
    logger.info("Starting dedicated scheduler process")
    scheduler.start()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down scheduler")
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    await stop_event.wait()

    if scheduler.running:
        scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
