from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation

from app.schemas.inventory.inventory_balance_schemas import (
    InventoryBalanceTableSchema,
)


import logging

logger = logging.getLogger(__name__)


# =====================================================
# MAPPER
# =====================================================
def _map_balance(
    balance: InventoryBalance,
    product: Product,
    location: InventoryLocation,
) -> InventoryBalanceTableSchema:
    return InventoryBalanceTableSchema(
        product_id=product.id,
        product_name=product.name,
        sku=product.sku,
        location_id=location.id,
        location_code=location.code,
        quantity=balance.quantity,
        min_stock_threshold=product.min_stock_threshold,
        updated_at=balance.updated_at,
    )
import time
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.inventory_balance_view import InventoryBalanceView

logger = logging.getLogger(__name__)

async def list_inventory_balances(
    db: AsyncSession,
    product_id: int | None,
    location_id: int | None,
    search: str | None,
    page: int,
    page_size: int,
):
    t0 = time.perf_counter()
    logger.info("[INV] start list_inventory_balances")

    # -------------------------------------------------
    # BUILD FILTERS (VIEW ONLY)
    # -------------------------------------------------
    filters = []

    if product_id:
        filters.append(InventoryBalanceView.product_id == product_id)

    if location_id:
        filters.append(InventoryBalanceView.location_id == location_id)

    if search:
        filters.append(
            InventoryBalanceView.product_name.ilike(f"%{search}%")
        )

    t1 = time.perf_counter()
    logger.info("[INV] filters built", extra={"t_filters": round(t1 - t0, 4)})

    # -------------------------------------------------
    # BUILD QUERY (SINGLE, SIMPLE QUERY)
    # -------------------------------------------------
    stmt = (
        select(
            InventoryBalanceView,
            func.count().over().label("total"),
        )
        .where(*filters)
        .order_by(
            InventoryBalanceView.product_name.asc(),
            InventoryBalanceView.location_code.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    t2 = time.perf_counter()
    logger.info("[INV] query built", extra={"t_query_build": round(t2 - t1, 4)})

    # -------------------------------------------------
    # EXECUTE QUERY
    # -------------------------------------------------
    t_exec_start = time.perf_counter()
    result = await db.execute(stmt)
    rows = result.all()
    t_exec_end = time.perf_counter()

    logger.info(
        "[INV] db.execute done",
        extra={
            "t_db": round(t_exec_end - t_exec_start, 4),
            "rows": len(rows),
        },
    )

    # -------------------------------------------------
    # EMPTY RESULT
    # -------------------------------------------------
    if not rows:
        t_end = time.perf_counter()
        logger.info(
            "[INV] empty result",
            extra={"t_total": round(t_end - t0, 4)},
        )
        return {"total": 0, "items": []}

    # -------------------------------------------------
    # EXTRACT TOTAL
    # -------------------------------------------------
    total = rows[0].total

    # -------------------------------------------------
    # MAP RESPONSE (NO JOIN OBJECTS ANYMORE)
    # -------------------------------------------------
    t_map_start = time.perf_counter()

    items = [
        {
            "product_id": r.product_id,
            "product_name": r.product_name,
            "sku": r.sku,
            "location_id": r.location_id,
            "location_code": r.location_code,
            "quantity": r.quantity,
            "min_stock_threshold": r.min_stock_threshold,  # 👈 ADD THIS
            "updated_at": r.updated_at,
        }
        for r, _ in rows
    ]


    t_map_end = time.perf_counter()
    logger.info(
        "[INV] mapping done",
        extra={"t_mapping": round(t_map_end - t_map_start, 4)},
    )

    # -------------------------------------------------
    # FINISH
    # -------------------------------------------------
    t_end = time.perf_counter()
    logger.info(
        "[INV] end list_inventory_balances",
        extra={
            "t_total": round(t_end - t0, 4),
            "page": page,
            "page_size": page_size,
        },
    )

    return {
        "total": total,
        "items": items,
    }


# =====================================================
# LOW STOCK ALERTS
# =====================================================
async def low_stock_alerts(db: AsyncSession):
    logger.info("Fetch low stock inventory balances")

    stmt = (
        select(InventoryBalance, Product, InventoryLocation)
        .join(Product, InventoryBalance.product_id == Product.id)
        .join(InventoryLocation, InventoryBalance.location_id == InventoryLocation.id)
        .where(
            Product.is_deleted.is_(False),
            InventoryLocation.is_deleted.is_(False),
            InventoryBalance.quantity <= Product.min_stock_threshold,
        )
    )

    result = await db.execute(stmt)

    return [
        _map_balance(balance, product, location)
        for balance, product, location in result.all()
    ]