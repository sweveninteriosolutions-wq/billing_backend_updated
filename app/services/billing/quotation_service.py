from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import os
import logging
from typing import List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc, delete
from sqlalchemy.orm import selectinload, noload

from app.models.billing.quotation_models import Quotation, QuotationItem
from app.models.masters.customer_models import Customer
from app.models.masters.product_models import Product
from app.models.enums.quotation_status import QuotationStatus

from app.schemas.billing.quotation_schemas import (
    QuotationCreate,
    QuotationUpdate,
    QuotationOut,
    QuotationItemOut,
    QuotationListData,
    QuotationListItem,
)

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity

logger = logging.getLogger(__name__)

GST_RATE = Decimal(os.getenv("GST_RATE", "0.18"))


def generate_item_signature(items: List[tuple[int, int]]) -> str:
    normalized = sorted(f"{pid}:{qty}" for pid, qty in items)
    return hashlib.sha256("|".join(normalized).encode()).hexdigest()


def _apply_gst_rates(q: Quotation) -> None:
    if q.is_inter_state:
        q.igst_rate = GST_RATE * Decimal("100")
        q.cgst_rate = Decimal("0.00")
        q.sgst_rate = Decimal("0.00")
    else:
        half = (GST_RATE * Decimal("100")) / Decimal("2")
        q.cgst_rate = half
        q.sgst_rate = half
        q.igst_rate = Decimal("0.00")


def _apply_gst_amounts(q: Quotation) -> None:
    if q.is_inter_state:
        q.igst_amount = q.subtotal_amount * GST_RATE
        q.cgst_amount = Decimal("0.00")
        q.sgst_amount = Decimal("0.00")
    else:
        half = (q.subtotal_amount * GST_RATE) / Decimal("2")
        q.cgst_amount = half
        q.sgst_amount = half
        q.igst_amount = Decimal("0.00")

    q.tax_amount = q.cgst_amount + q.sgst_amount + q.igst_amount
    q.total_amount = q.subtotal_amount + q.tax_amount


async def recalculate_totals(q: Quotation) -> None:
    q.subtotal_amount = sum(i.line_total for i in q.items if not i.is_deleted)
    _apply_gst_rates(q)
    _apply_gst_amounts(q)


async def _get_quotation_with_items(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.items),
            noload(Quotation.customer),
        )
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted.is_(False),
        )
    )
    q = result.scalar_one_or_none()
    if not q:
        raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)
    return q


async def _get_quotation_for_update(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.items),
            noload(Quotation.customer),
        )
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted.is_(False),
        )
        .with_for_update()
    )
    q = result.scalar_one_or_none()
    if not q:
        raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)
    return q


async def _fetch_products_map(
    db: AsyncSession,
    items,
) -> Dict[int, Product]:
    product_ids = {i.product_id for i in items}
    result = await db.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.is_deleted.is_(False),
        )
    )
    products = {p.id: p for p in result.scalars()}
    if len(products) != len(product_ids):
        raise AppException(
            404,
            "Invalid product IDs",
            ErrorCode.PRODUCT_NOT_FOUND,
        )
    return products


def _map_quotation(q: Quotation) -> QuotationOut:
    return QuotationOut(
        id=q.id,
        quotation_number=q.quotation_number,
        customer_id=q.customer_id,
        status=q.status,
        subtotal_amount=q.subtotal_amount,
        tax_amount=q.tax_amount,
        total_amount=q.total_amount,
        valid_until=q.valid_until,
        description=q.description,
        notes=q.notes,
        version=q.version,
        created_by=q.created_by_id,
        updated_by=q.updated_by_id,
        created_by_name=q.created_by_username,
        updated_by_name=q.updated_by_username,
        created_at=q.created_at,
        updated_at=q.updated_at,
        items=[
            QuotationItemOut(
                id=i.id,
                product_id=i.product_id,
                product_name=i.product_name,
                quantity=i.quantity,
                unit_price=i.unit_price,
                line_total=i.line_total,
            )
            for i in q.items
            if not i.is_deleted
        ],
    )


async def create_quotation(
    db: AsyncSession,
    payload: QuotationCreate,
    user,
) -> QuotationOut:
    customer = await db.get(Customer, payload.customer_id)
    if not customer or not customer.is_active:
        raise AppException(404, "Customer not found", ErrorCode.CUSTOMER_NOT_FOUND)

    if not payload.items:
        raise AppException(400, "Quotation must contain at least one item", ErrorCode.VALIDATION_ERROR)

    signature = generate_item_signature(
        [(i.product_id, i.quantity) for i in payload.items]
    )

    exists_draft = await db.scalar(
        select(
            select(Quotation.id)
            .where(
                Quotation.customer_id == payload.customer_id,
                Quotation.status == QuotationStatus.draft,
                Quotation.item_signature == signature,
                Quotation.is_deleted.is_(False),
            )
            .exists()
        )
    )

    if exists_draft:
        raise AppException(
            409,
            "A draft quotation with the same items already exists",
            ErrorCode.QUOTATION_DUPLICATE_DRAFT,
        )

    q = Quotation(
        quotation_number="TEMP",
        customer_id=payload.customer_id,
        status=QuotationStatus.draft,
        item_signature=signature,
        valid_until=payload.valid_until,
        description=payload.description,
        notes=payload.notes,
        is_inter_state=payload.is_inter_state,
        cgst_rate=Decimal("0.00"),
        sgst_rate=Decimal("0.00"),
        igst_rate=Decimal("0.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(q)

    products = await _fetch_products_map(db, payload.items)

    q.items = [
        QuotationItem(
            product_id=p.id,
            product_name=p.name,
            quantity=i.quantity,
            unit_price=p.price,
            line_total=p.price * i.quantity,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        for i in payload.items
        for p in [products[i.product_id]]
    ]

    await recalculate_totals(q)
    await db.flush()

    q.quotation_number = f"QT-{q.id:06d}"
    result = _map_quotation(q)

    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=q.quotation_number,
    )

    return result


async def get_quotation(
    db: AsyncSession,
    quotation_id: int,
) -> QuotationOut:
    q = await _get_quotation_with_items(db, quotation_id)
    return _map_quotation(q)


async def list_quotations(
    db: AsyncSession,
    customer_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    order: str = "desc",
) -> QuotationListData:
    base_query = (
        select(
            Quotation.id,
            Quotation.quotation_number,
            Customer.name.label("customer_name"),
            Quotation.status,
            Quotation.total_amount,
            Quotation.valid_until,
            func.count(QuotationItem.id).label("items_count"),
        )
        .join(Customer, Customer.id == Quotation.customer_id)
        .outerjoin(QuotationItem, QuotationItem.quotation_id == Quotation.id)
        .where(
            Quotation.is_deleted.is_(False),
            Customer.is_active.is_(True),
        )
        .group_by(Quotation.id, Customer.name)
    )

    if customer_id:
        base_query = base_query.where(Quotation.customer_id == customer_id)

    if status:
        base_query = base_query.where(Quotation.status == status)

    total = await db.scalar(
        select(func.count()).select_from(
            select(Quotation.id)
            .where(Quotation.is_deleted.is_(False))
            .subquery()
        )
    )

    sort_map = {
        "created_at": Quotation.created_at,
        "quotation_number": Quotation.quotation_number,
    }
    sort_col = sort_map.get(sort_by, Quotation.created_at)

    result = await db.execute(
        base_query
        .order_by(asc(sort_col) if order == "asc" else desc(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = result.all()

    items = [
        QuotationListItem(
            id=r.id,
            quotation_number=r.quotation_number,
            customer_name=r.customer_name,
            status=r.status,
            items_count=r.items_count,
            total_amount=r.total_amount,
            valid_until=r.valid_until,
        )
        for r in rows
    ]

    return QuotationListData(
        total=total or 0,
        items=items,
    )


async def update_quotation(
    db: AsyncSession,
    quotation_id: int,
    payload: QuotationUpdate,
    user,
) -> QuotationOut:
    q = await _get_quotation_with_items(db, quotation_id)

    if q.status != QuotationStatus.draft:
        raise AppException(400, "Only draft quotations editable", ErrorCode.QUOTATION_INVALID_STATE)

    if q.version != payload.version:
        raise AppException(409, "Version conflict", ErrorCode.QUOTATION_VERSION_CONFLICT)

    changes: list[str] = []

    if payload.items is not None:
        await db.execute(
            delete(QuotationItem).where(QuotationItem.quotation_id == q.id)
        )

        products = await _fetch_products_map(db, payload.items)

        db.add_all([
            QuotationItem(
                quotation_id=q.id,
                product_id=p.id,
                product_name=p.name,
                quantity=i.quantity,
                unit_price=p.price,
                line_total=p.price * i.quantity,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
            for i in payload.items
            for p in [products[i.product_id]]
        ])

        q.item_signature = generate_item_signature(
            [(i.product_id, i.quantity) for i in payload.items]
        )

        changes.append("items")

    if payload.description is not None and payload.description != q.description:
        q.description = payload.description
        changes.append("description")

    if payload.notes is not None and payload.notes != q.notes:
        q.notes = payload.notes
        changes.append("notes")

    if payload.valid_until is not None and payload.valid_until != q.valid_until:
        q.valid_until = payload.valid_until
        changes.append("valid_until")

    if not changes:
        return _map_quotation(q)

    q.version += 1
    q.updated_by_id = user.id
    q.updated_at = datetime.now(timezone.utc)

    await recalculate_totals(q)
    await db.flush()

    result = _map_quotation(q)

    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=q.quotation_number,
        changes=", ".join(changes),
    )

    return result


async def approve_quotation(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationOut:
    result = await db.execute(
        update(Quotation)
        .where(
            Quotation.id == quotation_id,
            Quotation.version == version,
            Quotation.status == QuotationStatus.draft,
            Quotation.is_deleted.is_(False),
        )
        .values(
            status=QuotationStatus.approved,
            version=Quotation.version + 1,
            updated_by_id=user.id,
        )
        .returning(Quotation.id)
    )

    approved_id = result.scalar_one_or_none()
    if not approved_id:
        raise AppException(409, "Quotation cannot be approved", ErrorCode.QUOTATION_CANNOT_APPROVE)

    q = await _get_quotation_with_items(db, approved_id)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.APPROVE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=q.quotation_number,
    )

    await db.commit()
    return _map_quotation(q)


async def delete_quotation(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationOut:
    q = await _get_quotation_with_items(db, quotation_id)

    if q.status != QuotationStatus.draft:
        raise AppException(409, "Only draft quotations can be deleted", ErrorCode.QUOTATION_CANNOT_DELETE)

    if q.version != version:
        raise AppException(409, "Version conflict", ErrorCode.QUOTATION_VERSION_CONFLICT)

    q.is_deleted = True
    q.version += 1
    q.updated_by_id = user.id

    result = _map_quotation(q)

    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DELETE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=q.quotation_number,
    )

    return result


async def convert_quotation_to_invoice(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationOut:
    q = await _get_quotation_for_update(db, quotation_id)

    if q.status != QuotationStatus.approved:
        raise AppException(409, "Only approved quotations can be converted to invoice", ErrorCode.QUOTATION_INVALID_STATE)

    if q.version != version:
        raise AppException(409, "Quotation modified by another process", ErrorCode.QUOTATION_VERSION_CONFLICT)

    q.status = QuotationStatus.converted_to_invoice
    q.version += 1
    q.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CONVERT_QUOTATION_TO_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=q.quotation_number,
    )

    await db.commit()

    q = await _get_quotation_with_items(db, quotation_id)
    return _map_quotation(q)
