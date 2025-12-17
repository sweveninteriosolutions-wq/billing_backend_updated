# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (user_router, auth_router, activity_router, customer_router, supplier_router, product_router
                         , inventory_balance_router, inventory_location_router, grn_router, quotation_router,
                         invoice_router, discount_router, payment_router, loyalty_token_router, stock_transfer_router,
                         complaint_router)
from app.core.db import Base, engine, init_models
from app.core.scheduler import scheduler
import logging

from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_handlers import (
    app_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    unhandled_exception_handler,
)
from app.core.exceptions import AppException

from app.core.logging import setup_logging
setup_logging()
from app.middleware.request_logging import request_logging_middleware

app = FastAPI(
    title="Backend Billing API",
    description="FastAPI + Supabase backend for Billing & Inventory",
    version="0.1.0"
)

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.middleware("http")(request_logging_middleware)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "Backend is running"}

# Register routers
app.include_router(user_router) 
app.include_router(auth_router)
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


@app.on_event("startup")
async def on_startup():
    await init_models()
    scheduler.start()