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
    grn_router,
    quotation_router,
    invoice_router,
    discount_router,
    payment_router,
    loyalty_token_router,
    stock_transfer_router,
    complaint_router,
)

from app.core.db import init_models
from app.core.scheduler import scheduler
from app.core.exceptions import AppException
from app.core.logging import setup_logging
from app.middleware.request_logging import request_logging_middleware
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
        logger.info("📦 Production mode: init_models() skipped")

    # ⚠️ Scheduler control
    if ENV == "production":
        if os.getenv("ENABLE_SCHEDULER", "false").lower() == "true":
            scheduler.start()
            logger.info("🕒 Scheduler started (production)")
        else:
            logger.info("🕒 Scheduler disabled (production)")
    else:
        scheduler.start()
        logger.info("🕒 Scheduler started (development)")

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
# MIDDLEWARE
# ------------------------------------------------------------------------------
app.middleware("http")(request_logging_middleware)

origins = [o.strip() for o in ALLOWED_ORIGINS if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
app.include_router(grn_router)
app.include_router(quotation_router)
app.include_router(invoice_router)
app.include_router(payment_router)
app.include_router(loyalty_token_router)
app.include_router(stock_transfer_router)
app.include_router(complaint_router)
