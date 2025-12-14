# app/services/inventory/inventory_balance_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import noload
from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.inventory_balance_schemas import (
    InventoryBalanceTableSchema,
)


def _map_balance(row) -> InventoryBalanceTableSchema:
    balance, product, location = row
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


# -----------------------------------
# LIST INVENTORY BALANCES
# -----------------------------------
async def list_inventory_balances(
    db: AsyncSession,
    product_id: int | None,
    location_id: int | None,
    search: str | None,
    page: int,
    page_size: int,
):
    stmt = (
        select(InventoryBalance, Product, InventoryLocation)
        .options(noload("*"))  
        .join(Product, InventoryBalance.product_id == Product.id)
        .join(InventoryLocation, InventoryBalance.location_id == InventoryLocation.id)
    )

    if product_id:
        stmt = stmt.where(Product.id == product_id)

    if location_id:
        stmt = stmt.where(InventoryLocation.id == location_id)

    if search:
        stmt = stmt.where(Product.name.ilike(f"%{search}%"))

    total = await db.scalar(
        select(func.count()).select_from(stmt.subquery())
    )

    result = await db.execute(
        stmt
        .order_by(Product.name.asc(), InventoryLocation.code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return total, [_map_balance(r) for r in result.all()]

# -----------------------------------
# LOW STOCK ALERTS
# -----------------------------------
async def low_stock_alerts(db: AsyncSession):
    stmt = (
        select(InventoryBalance, Product, InventoryLocation)
        .options(noload("*")) 
        .join(Product, InventoryBalance.product_id == Product.id)
        .join(InventoryLocation, InventoryBalance.location_id == InventoryLocation.id)
        .where(
            InventoryBalance.quantity <= Product.min_stock_threshold
        )
    )

    result = await db.execute(stmt)
    return [_map_balance(r) for r in result.all()]
