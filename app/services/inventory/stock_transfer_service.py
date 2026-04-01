# app/services/inventory/stock_transfer_service.py
# ERP-049 FIXED: get_stock_transfer used `StockTransferTableSchema.from_orm(row)` on a
#                raw SQLAlchemy Row object. In Pydantic v2, from_orm() is removed; the
#                correct call is model_validate(obj, from_attributes=True). Additionally,
#                a raw Row is not an ORM model instance — it won't have attribute access
#                working correctly for nested fields. Replaced with explicit constructor
#                call using named row fields, which is unambiguous and Pydantic-v2 safe.

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, aliased

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.constants.inventory_movement_type import InventoryMovementType

from app.models.inventory.stock_transfer_models import StockTransfer
from app.models.inventory.inventory_location_models import InventoryLocation
from app.models.inventory.inventory_balance_models import InventoryBalance
from app.models.inventory.stock_transfer_view import StockTransferView
from app.models.users.user_models import User
from app.models.masters.product_models import Product
from app.models.enums.stock_transfer_status import TransferStatus

from app.services.inventory.inventory_movement_service import apply_inventory_movement
from app.utils.activity_helpers import emit_activity

from app.schemas.inventory.stock_transfer_schemas import (
    StockTransferCreateSchema,
    StockTransferTableSchema,
)

logger = logging.getLogger(__name__)


async def get_inventory_summary(db: AsyncSession) -> dict:
    rows = await db.execute(
        select(
            InventoryLocation.code,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .join(InventoryBalance, InventoryBalance.location_id == InventoryLocation.id)
        .where(InventoryLocation.is_active.is_(True))
        .group_by(InventoryLocation.code)
    )
    summary = {"godown": 0, "showroom": 0}
    for code, qty in rows.all():
        if code.lower() == "godown":
            summary["godown"] = qty
        elif code.lower() == "showroom":
            summary["showroom"] = qty
    return summary


def generate_transfer_signature(
    *,
    product_id: int,
    quantity: int,
    from_location_id: int,
    to_location_id: int,
) -> str:
    payload = json.dumps(
        {"product_id": product_id, "quantity": int(quantity),
         "from": from_location_id, "to": to_location_id},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _map_transfer(t: StockTransfer) -> StockTransferTableSchema:
    return StockTransferTableSchema(
        id=t.id,
        product_id=t.product_id,
        quantity=t.quantity,
        from_location_id=t.from_location_id,
        to_location_id=t.to_location_id,
        status=t.status,
        transferred_by_id=t.transferred_by_id,
        transferred_by=t.transferred_by.username if t.transferred_by else None,
        completed_by_id=t.completed_by_id,
        completed_by=t.completed_by.username if t.completed_by else None,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def create_stock_transfer(
    db: AsyncSession,
    payload: StockTransferCreateSchema,
    user: User,
) -> StockTransferTableSchema:
    if payload.from_location_id == payload.to_location_id:
        raise AppException(400, "Source and destination locations must differ",
                           ErrorCode.STOCK_TRANSFER_INVALID_LOCATION)

    product_exists = await db.scalar(
        select(Product.id).where(Product.id == payload.product_id, Product.is_deleted.is_(False))
    )
    if not product_exists:
        raise AppException(400, "Invalid or inactive product", ErrorCode.STOCK_TRANSFER_INVALID_PRODUCT)

    count = await db.scalar(
        select(func.count())
        .select_from(InventoryLocation)
        .where(
            InventoryLocation.id.in_([payload.from_location_id, payload.to_location_id]),
            InventoryLocation.is_active.is_(True),
            InventoryLocation.is_deleted.is_(False),
        )
    )
    if count != 2:
        raise AppException(400, "Invalid or inactive location", ErrorCode.STOCK_TRANSFER_INVALID_LOCATION)

    balance_row = await db.execute(
        select(InventoryBalance)
        .where(
            InventoryBalance.product_id == payload.product_id,
            InventoryBalance.location_id == payload.from_location_id,
        )
        .with_for_update()
    )
    balance_obj = balance_row.scalar_one_or_none()
    current_qty = balance_obj.quantity if balance_obj else 0

    if current_qty < payload.quantity:
        raise AppException(409, "Insufficient stock at source location",
                           ErrorCode.STOCK_TRANSFER_INSUFFICIENT_STOCK)

    signature = generate_transfer_signature(
        product_id=payload.product_id,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
    )

    exists = await db.scalar(
        select(StockTransfer.id).where(
            StockTransfer.item_signature == signature,
            StockTransfer.status == TransferStatus.pending,
            StockTransfer.is_deleted.is_(False),
        )
    )
    if exists:
        raise AppException(409, "Duplicate pending stock transfer exists",
                           ErrorCode.STOCK_TRANSFER_DUPLICATE)

    transfer = StockTransfer(
        product_id=payload.product_id,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        transferred_by_id=user.id,
        item_signature=signature,
    )
    db.add(transfer)
    await db.flush()

    await emit_activity(
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.CREATE_STOCK_TRANSFER,
        actor_role=user.role.capitalize(), actor_email=user.username,
        target_name=str(transfer.id),
    )

    await db.commit()
    await db.refresh(transfer, attribute_names=["transferred_by"])
    return _map_transfer(transfer)


async def complete_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
    user: User,
) -> StockTransferTableSchema:
    transfer = await db.scalar(
        select(StockTransfer)
        .options(selectinload(StockTransfer.transferred_by))
        .where(StockTransfer.id == transfer_id, StockTransfer.is_deleted.is_(False))
        .with_for_update()
    )
    if not transfer:
        raise AppException(404, "Stock transfer not found", ErrorCode.NOT_FOUND)
    if transfer.status != TransferStatus.pending:
        raise AppException(400, "Only pending transfers can be completed",
                           ErrorCode.STOCK_TRANSFER_INVALID_STATUS)

    await apply_inventory_movement(
        db=db, product_id=transfer.product_id, location_id=transfer.from_location_id,
        quantity_change=-transfer.quantity, movement_type=InventoryMovementType.TRANSFER_OUT,
        reference_type="TRANSFER", reference_id=transfer.id, actor_user=user,
    )
    await apply_inventory_movement(
        db=db, product_id=transfer.product_id, location_id=transfer.to_location_id,
        quantity_change=transfer.quantity, movement_type=InventoryMovementType.TRANSFER_IN,
        reference_type="TRANSFER", reference_id=transfer.id, actor_user=user,
    )

    transfer.status = TransferStatus.completed
    transfer.completed_by_id = user.id
    transfer.updated_by_id = user.id
    transfer.updated_at = datetime.now(timezone.utc)

    await emit_activity(
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.COMPLETE_STOCK_TRANSFER,
        actor_role=user.role.capitalize(), actor_email=user.username,
        target_name=str(transfer.id),
    )

    await db.commit()
    await db.refresh(transfer, attribute_names=["transferred_by", "completed_by"])
    return _map_transfer(transfer)


async def cancel_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
    user: User,
) -> StockTransferTableSchema:
    transfer = await db.scalar(
        select(StockTransfer)
        .options(selectinload(StockTransfer.transferred_by))
        .where(StockTransfer.id == transfer_id, StockTransfer.is_deleted.is_(False))
        .with_for_update()
    )
    if not transfer:
        raise AppException(404, "Stock transfer not found", ErrorCode.NOT_FOUND)
    if transfer.status != TransferStatus.pending:
        raise AppException(400, "Only pending transfers can be cancelled",
                           ErrorCode.STOCK_TRANSFER_INVALID_STATUS)

    transfer.status = TransferStatus.cancelled
    transfer.completed_by_id = user.id
    transfer.updated_by_id = user.id
    transfer.updated_at = datetime.now(timezone.utc)

    await emit_activity(
        db=db, user_id=user.id, username=user.username,
        code=ActivityCode.CANCEL_STOCK_TRANSFER,
        actor_role=user.role.capitalize(), actor_email=user.username,
        target_name=str(transfer.id),
    )

    await db.commit()
    await db.refresh(transfer, attribute_names=["transferred_by", "completed_by"])
    return _map_transfer(transfer)


async def get_stock_transfer(
    db: AsyncSession,
    transfer_id: int,
) -> StockTransferTableSchema:
    """
    ERP-049 FIXED: Replaced `StockTransferTableSchema.from_orm(row)` on a raw SQLAlchemy
    Row with an explicit `StockTransferTableSchema(...)` constructor.

    from_orm() was removed in Pydantic v2. Additionally, a raw Row object from a
    multi-column select is NOT an ORM model instance — attribute access maps to the
    column labels, but nested model fields (like .transferred_by.username) won't work.
    The explicit constructor is unambiguous and handles both issues.
    """
    TransferredUser = aliased(User)
    CompletedUser = aliased(User)

    stmt = select(
        StockTransfer.id,
        StockTransfer.product_id,
        StockTransfer.quantity,
        StockTransfer.from_location_id,
        StockTransfer.to_location_id,
        StockTransfer.status,
        StockTransfer.transferred_by_id,
        (
            select(TransferredUser.username)
            .where(TransferredUser.id == StockTransfer.transferred_by_id)
            .scalar_subquery()
        ).label("transferred_by"),
        StockTransfer.completed_by_id,
        (
            select(CompletedUser.username)
            .where(CompletedUser.id == StockTransfer.completed_by_id)
            .scalar_subquery()
        ).label("completed_by"),
        StockTransfer.created_at,
        StockTransfer.updated_at,
    ).where(
        StockTransfer.id == transfer_id,
        StockTransfer.is_deleted.is_(False),
    )

    row = (await db.execute(stmt)).first()
    if not row:
        raise AppException(404, "Stock transfer not found", ErrorCode.NOT_FOUND)

    # ERP-049 FIXED: Explicit constructor — works with Pydantic v2, unambiguous column mapping.
    return StockTransferTableSchema(
        id=row.id,
        product_id=row.product_id,
        quantity=row.quantity,
        from_location_id=row.from_location_id,
        to_location_id=row.to_location_id,
        status=row.status,
        transferred_by_id=row.transferred_by_id,
        transferred_by=row.transferred_by,
        completed_by_id=row.completed_by_id,
        completed_by=row.completed_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_stock_transfers_view(
    db: AsyncSession,
    *,
    status: str | None,
    page: int,
    page_size: int,
):
    filters = []
    if status:
        filters.append(StockTransferView.status == status)

    total = await db.scalar(
        select(func.count()).select_from(StockTransferView).where(*filters)
    )
    rows = (
        await db.execute(
            select(StockTransferView)
            .where(*filters)
            .order_by(StockTransferView.transfer_date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    summary = await get_inventory_summary(db)
    return total or 0, rows, summary
