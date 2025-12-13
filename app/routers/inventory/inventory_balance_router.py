# app/routers/inventory/inventory_balance_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.services.inventory.inventory_balance_service import (
    list_inventory_balances,
    low_stock_alerts,
)
from app.schemas.inventory.inventory_balance_schemas import (
    InventoryBalanceListResponseSchema,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/inventory/balances", tags=["Inventory Balances"])


@router.get("/", response_model=InventoryBalanceListResponseSchema)
async def list_balances_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
    product_id: int | None = Query(None),
    location_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    total, rows = await list_inventory_balances(
        db, product_id, location_id, search, page, page_size
    )
    return {"msg": "Inventory balances fetched", "total": total, "data": rows}


@router.get("/low-stock", response_model=InventoryBalanceListResponseSchema)
async def low_stock_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    rows = await low_stock_alerts(db)
    return {"msg": "Low stock items", "total": len(rows), "data": rows}
