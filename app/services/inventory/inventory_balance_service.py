from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError

from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation

from app.schemas.inventory.inventory_balance_schemas import (
    InventoryBalanceTableSchema,
)

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity

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
):
    logger.info(
        "List inventory balances",
        extra={
            "product_id": product_id,
            "location_id": location_id,
            "search": search,
            "page": page,
            "page_size": page_size,
        },
    )

    # -------------------------------------------------
    # BASE FILTERS (BALANCE TABLE ONLY)
    # -------------------------------------------------
    base_filters = []

    if product_id:
        base_filters.append(InventoryBalance.product_id == product_id)

    if location_id:
        base_filters.append(InventoryBalance.location_id == location_id)

    if search:
        base_filters.append(
            InventoryBalance.product_id.in_(
                select(Product.id).where(
                    Product.name.ilike(f"%{search}%"),
                    Product.is_deleted.is_(False),
                )
            )
        )

    # -------------------------------------------------
    # FAST COUNT
    # -------------------------------------------------
    total = await db.scalar(
        select(func.count())
        .select_from(InventoryBalance)
        .where(*base_filters)
    )

    if not total:
        return {"total": 0, "items": []}

    # -------------------------------------------------
    # STEP 1: FETCH IDS ONLY (FAST SORT)
    # -------------------------------------------------
    id_stmt = (
        select(
            InventoryBalance.product_id,
            InventoryBalance.location_id,
        )
        .join(Product, InventoryBalance.product_id == Product.id)
        .join(InventoryLocation, InventoryBalance.location_id == InventoryLocation.id)
        .where(
            *base_filters,
            Product.is_deleted.is_(False),
            InventoryLocation.is_deleted.is_(False),
        )
        .order_by(Product.name.asc(), InventoryLocation.code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    id_rows = (await db.execute(id_stmt)).all()

    if not id_rows:
        return {"total": total, "items": []}

    # -------------------------------------------------
    # STEP 2: FETCH FULL ROWS (NO SORT)
    # -------------------------------------------------
    stmt = (
        select(InventoryBalance, Product, InventoryLocation)
        .join(Product, InventoryBalance.product_id == Product.id)
        .join(InventoryLocation, InventoryBalance.location_id == InventoryLocation.id)
        .where(
            InventoryBalance.product_id.in_([r.product_id for r in id_rows]),
            InventoryBalance.location_id.in_([r.location_id for r in id_rows]),
        )
    )

    result = await db.execute(stmt)

    # Preserve ordering
    order_map = {
        (r.product_id, r.location_id): i
        for i, r in enumerate(id_rows)
    }

    rows = result.all()
    rows.sort(
        key=lambda r: order_map[(r[0].product_id, r[0].location_id)]
    )

    return {
        "total": total or 0,
        "items": [
            _map_balance(balance, product, location)
            for balance, product, location in rows
        ],
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