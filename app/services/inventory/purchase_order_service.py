# app/services/inventory/purchase_order_service.py
import logging
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload

from app.models.inventory.purchase_order_models import PurchaseOrder, PurchaseOrderItem
from app.models.masters.supplier_models import Supplier
from app.models.inventory.inventory_location_models import InventoryLocation

from app.schemas.inventory.purchase_order_schemas import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderOut,
    POItemOut,
    PurchaseOrderListItem,
    PurchaseOrderListData,
)

from app.constants.activity_codes import ActivityCode
from app.constants.error_codes import ErrorCode
# ERP-034 FIXED: GST_RATE imported from config.py — single source of truth.
from app.core.config import GST_RATE
from app.core.exceptions import AppException
from app.utils.activity_helpers import emit_activity

logger = logging.getLogger(__name__)


def _map_po(po: PurchaseOrder) -> PurchaseOrderOut:
    supplier_name = po.supplier.name if po.supplier else None
    location_name = po.location.name if po.location else None
    return PurchaseOrderOut(
        id=po.id,
        po_number=po.po_number,
        supplier_id=po.supplier_id,
        supplier_name=supplier_name,
        location_id=po.location_id,
        location_name=location_name,
        status=po.status,
        expected_date=po.expected_date,
        notes=po.notes,
        gross_amount=po.gross_amount,
        tax_amount=po.tax_amount,
        net_amount=po.net_amount,
        version=po.version,
        created_at=po.created_at,
        updated_at=po.updated_at,
        items=[
            POItemOut(
                id=i.id,
                product_id=i.product_id,
                product_name=i.product.name if i.product else None,
                quantity_ordered=i.quantity_ordered,
                quantity_received=i.quantity_received,
                unit_cost=i.unit_cost,
                line_total=i.line_total,
            )
            for i in po.items
        ],
    )


async def _fetch_po_with_relations(db: AsyncSession, po_id: int) -> PurchaseOrder:
    result = await db.execute(
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.items).selectinload(PurchaseOrderItem.product),
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.location),
        )
        .where(PurchaseOrder.id == po_id, PurchaseOrder.is_deleted.is_(False))
    )
    po = result.scalar_one_or_none()
    if not po:
        raise AppException(404, "Purchase order not found", ErrorCode.PURCHASE_ORDER_NOT_FOUND)
    return po


async def create_purchase_order(
    db: AsyncSession, payload: PurchaseOrderCreate, user
) -> PurchaseOrderOut:
    # Validate supplier
    supplier = await db.get(Supplier, payload.supplier_id)
    if not supplier or supplier.is_deleted:
        raise AppException(404, "Supplier not found", ErrorCode.SUPPLIER_NOT_FOUND)

    # Validate location
    location = await db.get(InventoryLocation, payload.location_id)
    if not location or not location.is_active:
        raise AppException(404, "Inventory location not found or inactive", ErrorCode.LOCATION_NOT_FOUND)

    if not payload.items:
        raise AppException(400, "Purchase order must have at least one item", ErrorCode.VALIDATION_ERROR)

    gross = Decimal("0.00")
    items = []
    for item in payload.items:
        line_total = item.unit_cost * item.quantity_ordered
        gross += line_total
        items.append(
            PurchaseOrderItem(
                product_id=item.product_id,
                quantity_ordered=item.quantity_ordered,
                quantity_received=0,
                unit_cost=item.unit_cost,
                line_total=line_total,
            )
        )

    tax = gross * GST_RATE
    net = gross + tax

    # ERP-022 FIXED: Use timezone-aware datetime.now(timezone.utc) instead of deprecated utcnow().
    po = PurchaseOrder(
        po_number=(
            f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            f"-{__import__('os').urandom(2).hex().upper()}"
        ),
        supplier_id=payload.supplier_id,
        location_id=payload.location_id,
        status="draft",
        expected_date=payload.expected_date,
        notes=payload.notes,
        gross_amount=gross,
        tax_amount=tax,
        net_amount=net,
        version=1,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    po.items.extend(items)

    db.add(po)
    await db.flush()
    await db.refresh(po, attribute_names=["items", "supplier", "location"])

    result = _map_po(po)

    # ERP-020 FIXED: Use correct activity code CREATE_PURCHASE_ORDER (was CREATE_STOCK_TRANSFER).
    # ERP-014 pattern: emit_activity BEFORE commit.
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_PURCHASE_ORDER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=po.po_number,
    )

    await db.commit()
    return result


async def list_purchase_orders(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    supplier_id: int | None = None,
    status: str | None = None,
) -> PurchaseOrderListData:

    query = (
        select(PurchaseOrder)
        .options(
            selectinload(PurchaseOrder.supplier),
            selectinload(PurchaseOrder.location),
            selectinload(PurchaseOrder.items),
        )
        .where(PurchaseOrder.is_deleted.is_(False))
        .order_by(desc(PurchaseOrder.created_at))
    )

    if supplier_id:
        query = query.where(PurchaseOrder.supplier_id == supplier_id)
    if status:
        query = query.where(PurchaseOrder.status == status)

    total_q = select(func.count(PurchaseOrder.id)).where(PurchaseOrder.is_deleted.is_(False))
    if supplier_id:
        total_q = total_q.where(PurchaseOrder.supplier_id == supplier_id)
    if status:
        total_q = total_q.where(PurchaseOrder.status == status)

    total = await db.scalar(total_q)
    rows = (await db.execute(query.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    items = [
        PurchaseOrderListItem(
            id=po.id,
            po_number=po.po_number,
            supplier_name=po.supplier.name if po.supplier else "—",
            location_name=po.location.name if po.location else "—",
            status=po.status,
            net_amount=po.net_amount,
            expected_date=po.expected_date,
            items_count=len(po.items),
            created_at=po.created_at,
        )
        for po in rows
    ]

    return PurchaseOrderListData(total=total or 0, items=items)


async def get_purchase_order(db: AsyncSession, po_id: int) -> PurchaseOrderOut:
    po = await _fetch_po_with_relations(db, po_id)
    return _map_po(po)


async def submit_purchase_order(db: AsyncSession, po_id: int, version: int, user) -> PurchaseOrderOut:
    """
    ERP-021 FIXED: Version is now required and checked to prevent concurrent double-submit.
    Caller must pass the current version from their fetched PO.
    """
    result = await db.execute(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.version == version,
            PurchaseOrder.status == "draft",
        )
        .with_for_update()
    )
    po = result.scalar_one_or_none()
    if not po:
        raise AppException(
            409,
            "Purchase order not found, not in draft state, or version conflict",
            ErrorCode.PURCHASE_ORDER_INVALID_STATE,
        )

    po.status = "submitted"
    po.version += 1
    po.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.SUBMIT_PURCHASE_ORDER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=po.po_number,
    )

    await db.commit()
    return await _fetch_po_with_relations(db, po_id)


async def approve_purchase_order(db: AsyncSession, po_id: int, version: int, user) -> PurchaseOrderOut:
    """
    ERP-021 FIXED: Version is now required and checked.
    """
    result = await db.execute(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.version == version,
            PurchaseOrder.status == "submitted",
        )
        .with_for_update()
    )
    po = result.scalar_one_or_none()
    if not po:
        raise AppException(
            409,
            "Purchase order not found, not in submitted state, or version conflict",
            ErrorCode.PURCHASE_ORDER_INVALID_STATE,
        )

    po.status = "approved"
    po.approved_by_id = user.id
    po.version += 1
    po.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.APPROVE_PURCHASE_ORDER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=po.po_number,
    )

    await db.commit()
    return await _fetch_po_with_relations(db, po_id)


async def cancel_purchase_order(db: AsyncSession, po_id: int, version: int, user) -> PurchaseOrderOut:
    """
    ERP-021 FIXED: Version is now required and checked.
    """
    result = await db.execute(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == po_id,
            PurchaseOrder.is_deleted.is_(False),
            PurchaseOrder.version == version,
        )
        .with_for_update()
    )
    po = result.scalar_one_or_none()
    if not po:
        raise AppException(
            409,
            "Purchase order not found or version conflict",
            ErrorCode.PURCHASE_ORDER_INVALID_STATE,
        )

    if po.status in ("fulfilled", "cancelled"):
        raise AppException(
            400,
            "Cannot cancel a fulfilled or already cancelled PO",
            ErrorCode.PURCHASE_ORDER_INVALID_STATE,
        )

    po.status = "cancelled"
    po.version += 1
    po.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CANCEL_PURCHASE_ORDER,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=po.po_number,
    )

    await db.commit()
    return await _fetch_po_with_relations(db, po_id)
