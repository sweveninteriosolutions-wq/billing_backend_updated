# app/routers/inventory/inventory_movement_router.py
"""
Inventory Movement ledger — read-only endpoints.
All stock changes are recorded here automatically by other services.
No write operations are exposed — movements are immutable.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse
from app.models.inventory.inventory_movement_models import InventoryMovement
from app.models.masters.product_models import Product
from app.models.inventory.inventory_location_models import InventoryLocation
from app.schemas.inventory.inventory_movement_schemas import (
    InventoryMovementOut,
    InventoryMovementListData,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/inventory/movements",
    tags=["Inventory Movements"],
)


# =========================
# LIST MOVEMENTS (paginated, filterable)
# =========================
@router.get("/", response_model=APIResponse[InventoryMovementListData])
async def list_movements(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
    product_id: Optional[int] = Query(None),
    location_id: Optional[int] = Query(None),
    reference_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    base_query = select(InventoryMovement).options(
        selectinload(InventoryMovement.product),
        selectinload(InventoryMovement.location),
    )

    if product_id:
        base_query = base_query.where(InventoryMovement.product_id == product_id)
    if location_id:
        base_query = base_query.where(InventoryMovement.location_id == location_id)
    if reference_type:
        base_query = base_query.where(
            InventoryMovement.reference_type == reference_type.upper()
        )

    # Total count
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated rows
    rows_q = (
        base_query
        .order_by(desc(InventoryMovement.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(rows_q)
    movements = result.scalars().all()

    items = [
        InventoryMovementOut(
            id=m.id,
            product_id=m.product_id,
            product_name=m.product.name if m.product else None,
            product_sku=m.product.sku if m.product else None,
            location_id=m.location_id,
            location_name=m.location.name if m.location else None,
            quantity_change=m.quantity_change,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            created_at=m.created_at,
            created_by=m.created_by_id,
            created_by_name=m.created_by.username if m.created_by else None,
        )
        for m in movements
    ]

    return success_response(
        "Inventory movements retrieved",
        InventoryMovementListData(total=total, items=items),
    )
