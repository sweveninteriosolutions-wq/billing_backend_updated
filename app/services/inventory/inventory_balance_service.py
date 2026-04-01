# app/services/inventory/inventory_balance_service.py
# ERP-035 FIXED: Removed dead _map_balance function and duplicate import blocks.
#                The file previously had two separate import sections (one from the
#                old direct-query approach, one from the view-based approach) causing
#                duplicate `import logging` and duplicate `from sqlalchemy import select`.
# ERP-055 FIXED: Removed all time.perf_counter() profiling instrumentation.
#                Profiling belongs in a dev/staging branch or APM tool, not production code.

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.inventory_balance_view import InventoryBalanceView
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.inventory_balance_schemas import InventoryBalanceTableSchema

logger = logging.getLogger(__name__)


# =====================================================
# LIST INVENTORY BALANCES
# =====================================================
async def list_inventory_balances(
    db: AsyncSession,
    product_id: int | None,
    location_id: int | None,
    search: str | None,
    page: int,
    page_size: int,
) -> dict:
    filters = []

    if product_id:
        filters.append(InventoryBalanceView.product_id == product_id)
    if location_id:
        filters.append(InventoryBalanceView.location_id == location_id)
    if search:
        filters.append(InventoryBalanceView.product_name.ilike(f"%{search}%"))

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

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return {"total": 0, "items": []}

    total = rows[0].total

    items = [
        {
            "product_id": r.product_id,
            "product_name": r.product_name,
            "sku": r.sku,
            "location_id": r.location_id,
            "location_code": r.location_code,
            "quantity": r.quantity,
            "min_stock_threshold": r.min_stock_threshold,
            "updated_at": r.updated_at,
        }
        for r, _ in rows
    ]

    return {"total": total, "items": items}


# =====================================================
# LOW STOCK ALERTS
# =====================================================
async def low_stock_alerts(db: AsyncSession) -> list[InventoryBalanceTableSchema]:
    """Return all product+location combinations where stock is at or below threshold."""
    logger.info("Fetching low-stock inventory balances")

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
        InventoryBalanceTableSchema(
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            location_id=location.id,
            location_code=location.code,
            quantity=balance.quantity,
            min_stock_threshold=product.min_stock_threshold,
            updated_at=balance.updated_at,
        )
        for balance, product, location in result.all()
    ]
