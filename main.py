# main.py
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError

from app.routers import (
    user_router,
    auth_router,
    activity_router,
    customer_router,
    supplier_router,
    product_router,
    inventory_balance_router,
    inventory_location_router,
    inventory_movement_router,
    grn_router,
    quotation_router,
    invoice_router,
    discount_router,
    payment_router,
    loyalty_token_router,
    stock_transfer_router,
    complaint_router,
    file_upload_router,
    purchase_order_router,
    warehouse_router,
    reports_router,
)

from app.core.db import init_models
from app.core.scheduler import scheduler
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.middleware.request_logging import request_logging_middleware
from app.middleware.rate_limiter import RateLimitMiddleware
# ERP-025 FIXED: ActivityLoggerMiddleware was defined but never registered. Now imported and added.
from app.middleware.activity_logger import ActivityLoggerMiddleware
from app.core.error_handlers import (
    app_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    unhandled_exception_handler,
)

# ------------------------------------------------------------------------------
# ENV CONFIG
# ------------------------------------------------------------------------------
ENV = os.getenv("APP_ENV", "development")
APP_NAME = "Varasidhi Furnitures – Billing & Inventory API"
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

# ------------------------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------------------------
setup_logging()
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# LIFESPAN (PRODUCTION SAFE)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting application")

    # ✅ DB init ONLY in development
    if ENV == "development":
        await init_models()
        logger.info("📦 Database models initialized (development)")
    else:
        logger.info("📦 Production mode: init_models() skipped — use Alembic migrations")

    # ⚠️ Scheduler control — SEC-P0-3 FIXED
    # In production, the scheduler MUST run in a dedicated process (app/core/run_scheduler.py),
    # not here. Running it here causes every Gunicorn worker to start its own scheduler
    # instance, so cron jobs fire N times per schedule (once per worker).
    # ENABLE_SCHEDULER must be "true" ONLY in the dedicated scheduler container/process.
    # Never set ENABLE_SCHEDULER=true on a multi-worker API container.
    if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
        if ENV == "production":
            logger.warning(
                "SEC-P0-3 WARNING: ENABLE_SCHEDULER=true on an API process. "
                "In production, the scheduler should run in a DEDICATED single-replica "
                "container using app/core/run_scheduler.py. "
                "If this process has multiple workers, jobs will fire once per worker."
            )
        scheduler.start()
        logger.info("🕒 Scheduler started (ENABLE_SCHEDULER=true)")
    else:
        logger.info("🕒 Scheduler disabled (ENABLE_SCHEDULER=false) — use app/core/run_scheduler.py")

    yield

    logger.info("🛑 Shutting down application")
    if scheduler.running:
        scheduler.shutdown()

# ------------------------------------------------------------------------------
# APP INIT
# ------------------------------------------------------------------------------
app = FastAPI(
    title=APP_NAME,
    description="Backend API for Billing & Inventory ERP",
    version=APP_VERSION,
    docs_url="/docs" if ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# ------------------------------------------------------------------------------
# EXCEPTION HANDLERS
# ------------------------------------------------------------------------------
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ------------------------------------------------------------------------------
# MIDDLEWARE (order matters — outermost = first to run)
# 1. Rate limiter (blocks first, before any work)
# 2. CORS (handles preflight)
# 3. Activity logger (logs mutating requests with user context)
# 4. Request logging (innermost — records timing)
# ------------------------------------------------------------------------------
app.add_middleware(RateLimitMiddleware)

origins = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

# SEC-P2-1 FIXED: Validate CORS config at startup in production.
# If CORS_ORIGINS is empty or contains a wildcard in production, the server
# either allows nothing (frontend breaks) or allows everything (security breach).
if ENV == "production":
    if not origins:
        raise ValueError(
            "SECURITY ERROR (SEC-P2-1): CORS_ORIGINS must be set in production. "
            "Set it to your frontend domain(s), e.g. https://app.yourdomain.com"
        )
    if "*" in origins:
        raise ValueError(
            "SECURITY ERROR (SEC-P2-1): Wildcard '*' is not allowed in CORS_ORIGINS "
            "in production. Specify exact frontend origin(s)."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ERP-025 FIXED: Middleware is now registered. Runs after auth sets request.state.user.
app.add_middleware(ActivityLoggerMiddleware)

app.middleware("http")(request_logging_middleware)

# ------------------------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------------------------
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": "billing-inventory-api",
        "environment": ENV,
        "version": APP_VERSION,
    }

# ------------------------------------------------------------------------------
# ROUTERS
# ------------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(activity_router)
app.include_router(customer_router)
app.include_router(supplier_router)
app.include_router(product_router)
app.include_router(discount_router)
app.include_router(inventory_balance_router)
app.include_router(inventory_location_router)
app.include_router(inventory_movement_router)
app.include_router(grn_router)
app.include_router(quotation_router)
app.include_router(invoice_router)
app.include_router(payment_router)
app.include_router(loyalty_token_router)
app.include_router(stock_transfer_router)
app.include_router(complaint_router)
app.include_router(file_upload_router)
app.include_router(purchase_order_router)
app.include_router(warehouse_router)
app.include_router(reports_router)
