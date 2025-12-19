from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.services.inventory.inventory_balance_service import (
    list_inventory_balances,
    low_stock_alerts,
)

from app.schemas.inventory.inventory_balance_schemas import (
    InventoryBalanceTableSchema,
    InventoryBalanceListData
)

router = APIRouter(
    prefix="/inventory/balances",
    tags=["Inventory Balances"],
)


# =========================
# LIST INVENTORY BALANCES
# =========================
@router.get(
    "/",
    response_model=APIResponse[InventoryBalanceListData],
)
async def list_inventory_balances_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
    product_id: int | None = Query(None),
    location_id: int | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    result = await list_inventory_balances(
        db=db,
        product_id=product_id,
        location_id=location_id,
        search=search,
        page=page,
        page_size=page_size,
    )

    return success_response(
        "Inventory balances fetched successfully",
        result,
    )


# =========================
# LOW STOCK ALERTS
# =========================
@router.get(
    "/low-stock",
    response_model=APIResponse[list[InventoryBalanceTableSchema]],
)
async def low_stock_alerts_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    items = await low_stock_alerts(db)

    return success_response(
        "Low stock items fetched successfully",
        items,
    )
