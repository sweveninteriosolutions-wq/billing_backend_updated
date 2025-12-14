# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (user_router, auth_router, activity_router, customer_router, supplier_router, product_router
                         , inventory_balance_router, inventory_location_router, grn_router)
from app.core.db import Base, engine, init_models

app = FastAPI(
    title="Backend Billing API",
    description="FastAPI + Supabase backend for Billing & Inventory",
    version="0.1.0"
)
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
app.include_router(inventory_balance_router)  #added
app.include_router(inventory_location_router)
app.include_router(grn_router)

#added


@app.on_event("startup")
async def on_startup():
    await init_models()
