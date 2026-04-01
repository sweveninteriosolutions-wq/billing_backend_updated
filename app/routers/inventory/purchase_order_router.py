# app/routers/inventory/purchase_order_router.py
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

from app.schemas.inventory.purchase_order_schemas import (
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderListData,
)
from app.services.inventory.purchase_order_service import (
    create_purchase_order,
    list_purchase_orders,
    get_purchase_order,
    submit_purchase_order,
    approve_purchase_order,
    cancel_purchase_order,
)

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])


@router.post("", response_model=APIResponse[PurchaseOrderOut])
async def create_po_api(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    po = await create_purchase_order(db, payload, user)
    return success_response("Purchase order created", po)


@router.get("", response_model=APIResponse[PurchaseOrderListData])
async def list_pos_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    supplier_id: Optional[int] = None,
    status: Optional[str] = None,
):
    data = await list_purchase_orders(
        db, page=page, page_size=page_size, supplier_id=supplier_id, status=status
    )
    return success_response("Purchase orders retrieved", data)


@router.get("/{po_id}", response_model=APIResponse[PurchaseOrderOut])
async def get_po_api(
    po_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
):
    po = await get_purchase_order(db, po_id)
    return success_response("Purchase order retrieved", po)


@router.post("/{po_id}/submit", response_model=APIResponse[PurchaseOrderOut])
async def submit_po_api(
    po_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    po = await submit_purchase_order(db, po_id, user)
    return success_response("Purchase order submitted", po)


@router.post("/{po_id}/approve", response_model=APIResponse[PurchaseOrderOut])
async def approve_po_api(
    po_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "manager"])),
):
    po = await approve_purchase_order(db, po_id, user)
    return success_response("Purchase order approved", po)


@router.post("/{po_id}/cancel", response_model=APIResponse[PurchaseOrderOut])
async def cancel_po_api(
    po_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    po = await cancel_purchase_order(db, po_id, user)
    return success_response("Purchase order cancelled", po)
