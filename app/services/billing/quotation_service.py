from decimal import Decimal
import hashlib
from typing import List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from sqlalchemy.orm import noload

from app.models.billing.quotation_models import Quotation, QuotationItem
from app.models.masters.customer_models import Customer
from app.models.masters.product_models import Product
from app.models.enums.quotation_status import QuotationStatus

from app.schemas.billing.quotation_schemas import (
    QuotationCreate,
    QuotationUpdate,
    QuotationOut,
    QuotationResponse,
    QuotationListResponse,
    QuotationItemOut,
)

from app.utils.activity_helpers import emit_activity
import os
from app.constants.activity_codes import ActivityCode


GST_RATE = Decimal(
    os.getenv("GST_RATE", "0.18")  
)


# =====================================================
# SIGNATURE (DEDUP)
# =====================================================

def generate_item_signature(items: List[tuple[int, int]]) -> str:
    """
    items = [(product_id, quantity), ...]
    Order independent
    """
    normalized = sorted(f"{pid}:{qty}" for pid, qty in items)
    raw = "|".join(normalized)
    return hashlib.sha256(raw.encode()).hexdigest()


# =====================================================
# INTERNAL HELPERS
# =====================================================

async def _get_quotation_with_items(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .options(
            selectinload(Quotation.items),
            selectinload(Quotation.customer),  # 👈 IMPORTANT
            # selectinload(Quotation.created_by),   # 👈 User relationship
            # selectinload(Quotation.updated_by),
        )
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted == False,
        )
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(404, "Quotation not found")
    return quotation

async def _get_quotation_for_update(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted == False,
        )
        .with_for_update()
    )

    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(404, "Quotation not found")

    return quotation


async def _fetch_products_map(
    db: AsyncSession,
    items,
) -> Dict[int, Product]:
    """
    Bulk fetch products → avoids N+1 queries
    """
    product_ids = {i.product_id for i in items}

    result = await db.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.is_deleted == False,
        )
    )

    products = {p.id: p for p in result.scalars()}

    if len(products) != len(product_ids):
        missing = product_ids - products.keys()
        raise HTTPException(
            status_code=404,
            detail=f"Invalid product IDs: {list(missing)}",
        )

    return products


async def recalculate_totals(quotation: Quotation) -> None:
    subtotal = Decimal("0.00")

    for item in quotation.items:
        if not item.is_deleted:
            subtotal += item.line_total

    quotation.subtotal_amount = subtotal
    quotation.tax_amount = subtotal * GST_RATE
    quotation.total_amount = subtotal + quotation.tax_amount

async def _get_quotation_for_update(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    """
    Fetch quotation WITH ROW LOCK.
    Use ONLY for critical state transitions.
    """
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .options(
            noload("*")  # 🔒 ABSOLUTE GUARANTEE: NO JOINS
        )
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted == False,
        )
        .with_for_update()
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(404, "Quotation not found")
    return quotation


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
            for i in q.items if not i.is_deleted
        ],
    )


# =====================================================
# CREATE QUOTATION
# =====================================================

async def create_quotation(
    db: AsyncSession,
    payload: QuotationCreate,
    user,
) -> QuotationResponse:

    customer = await db.get(Customer, payload.customer_id)
    if not customer or not customer.is_active:
        raise HTTPException(404, "Customer not found")

    items_for_signature = [
        (i.product_id, i.quantity) for i in payload.items
    ]
    signature = generate_item_signature(items_for_signature)

    existing = await db.scalar(
        select(Quotation.id).where(
            Quotation.customer_id == payload.customer_id,
            Quotation.status == QuotationStatus.draft,
            Quotation.item_signature == signature,
            Quotation.is_deleted == False,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A draft quotation with the same items already exists",
        )

    quotation = Quotation(
        quotation_number="TEMP",
        customer_id=payload.customer_id,
        status=QuotationStatus.draft,
        item_signature=signature,
        valid_until=payload.valid_until,
        description=payload.description,
        notes=payload.notes,
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(quotation)
    await db.flush()
    quotation.quotation_number = f"QT-{quotation.id:06d}"

    products_map = await _fetch_products_map(db, payload.items)

    for item in payload.items:
        product = products_map[item.product_id]

        db.add(
            QuotationItem(
                quotation_id=quotation.id,
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=product.price,
                line_total=product.price * item.quantity,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )


    await db.flush()
    subtotal = Decimal("0.00")

    for item in payload.items:
        product = products_map[item.product_id]
        subtotal += product.price * item.quantity

    quotation.subtotal_amount = subtotal
    quotation.tax_amount = subtotal * GST_RATE
    quotation.total_amount = subtotal + quotation.tax_amount


    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
    )

    await db.commit()

    # SAFE refetch
    quotation = await _get_quotation_with_items(db, quotation.id)

    # SAFE mapping (NO lazy props)
    return QuotationResponse(
        message="Quotation created successfully",
        data=_map_quotation(quotation),
    )


# =====================================================
# GET ONE
# =====================================================

async def get_quotation(
    db: AsyncSession,
    quotation_id: int,
) -> QuotationResponse:
    quotation = await _get_quotation_with_items(db, quotation_id)
    return QuotationResponse(message="Quotation retrieved successfully", data=_map_quotation(quotation))


# =====================================================
# LIST
# =====================================================

async def list_quotations(
    db: AsyncSession,
    customer_id: int | None,
    status: str | None,
    limit: int,
    offset: int,
    sort_by: str,
    order: str,
) -> QuotationListResponse:

    query = select(Quotation).where(Quotation.is_deleted == False)

    if customer_id:
        query = query.where(Quotation.customer_id == customer_id)
    if status:
        query = query.where(Quotation.status == status)

    sort_map = {
        "created_at": Quotation.created_at,
        "quotation_number": Quotation.quotation_number,
    }
    sort_col = sort_map.get(sort_by, Quotation.created_at)
    query = query.order_by(asc(sort_col) if order == "asc" else desc(sort_col))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    result = await db.execute(
        query.options(selectinload(Quotation.items))
        .offset(offset)
        .limit(limit)
    )

    rows = result.scalars().all()

    return QuotationListResponse(
        message="Quotations retrieved successfully",
        total=total or 0,
        data=[_map_quotation(q) for q in rows],
    )


# =====================================================
# UPDATE (DRAFT ONLY)
# =====================================================

async def update_quotation(
    db: AsyncSession,
    quotation_id: int,
    payload: QuotationUpdate,
    user,
) -> QuotationResponse:

    quotation = await _get_quotation_with_items(db, quotation_id)

    if quotation.status != QuotationStatus.draft:
        raise HTTPException(400, "Only draft quotations can be edited")

    if quotation.version != payload.version:
        raise HTTPException(409, "Quotation modified by another process")

    changes: list[str] = []

    if payload.items is not None:
        for old in quotation.items:
            old.is_deleted = True

        products_map = await _fetch_products_map(db, payload.items)

        for item in payload.items:
            product = products_map[item.product_id]
            quotation.items.append(
                QuotationItem(
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price=product.price,
                    line_total=product.price * item.quantity,
                    created_by_id=user.id,
                    updated_by_id=user.id,
                )
            )

        quotation.item_signature = generate_item_signature(
            [(i.product_id, i.quantity) for i in payload.items]
        )
        changes.append("items")

    if payload.description is not None:
        quotation.description = payload.description
        changes.append("description")

    if payload.notes is not None:
        quotation.notes = payload.notes
        changes.append("notes")

    if payload.valid_until is not None:
        quotation.valid_until = payload.valid_until
        changes.append("valid_until")

    quotation.updated_by_id = user.id
    quotation.version += 1

    await db.flush()
    await recalculate_totals(quotation)
    await db.commit()

    quotation = await _get_quotation_with_items(db, quotation.id)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
        changes=", ".join(changes) if changes else "no changes",
    )

    return QuotationResponse(message="Quotation updated successfully", data=_map_quotation(quotation))


# =====================================================
# APPROVE
# =====================================================

async def approve_quotation(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationResponse:

    stmt = (
        update(Quotation)
        .where(
            Quotation.id == quotation_id,
            Quotation.version == version,
            Quotation.status == QuotationStatus.draft,
            Quotation.is_deleted == False,
        )
        .values(
            status=QuotationStatus.approved,
            version=Quotation.version + 1,
            updated_by_id=user.id,
        )
        .returning(Quotation.id)
    )

    result = await db.execute(stmt)
    approved_id = result.scalar_one_or_none()

    if not approved_id:
        raise HTTPException(409, "Quotation cannot be approved")

    await db.commit()
    quotation = await _get_quotation_with_items(db, approved_id)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.APPROVE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
    )

    return QuotationResponse(message="Quotation approved successfully", data=_map_quotation(quotation))


# =====================================================
# DELETE (DRAFT ONLY)
# =====================================================

async def delete_quotation(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationResponse:

    stmt = (
        update(Quotation)
        .where(
            Quotation.id == quotation_id,
            Quotation.version == version,
            Quotation.status == QuotationStatus.draft,
            Quotation.is_deleted == False,
        )
        .values(
            is_deleted=True,
            version=Quotation.version + 1,
            updated_by_id=user.id,
        )
        .returning(Quotation.id)
    )

    result = await db.execute(stmt)
    deleted_id = result.scalar_one_or_none()

    if not deleted_id:
        raise HTTPException(409, "Only draft quotations can be deleted")

    await db.commit()
    quotation = await _get_quotation_with_items(db, deleted_id)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DELETE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
    )

    return QuotationResponse(message="Quotation deleted successfully", data=_map_quotation(quotation))


# =====================================================
# CONVERT → INVOICE (STUB)
# =====================================================
async def convert_quotation_to_invoice(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationResponse:

    try:
        # 1️⃣ LOCK ONLY THE QUOTATION ROW
        quotation = await _get_quotation_for_update(db, quotation_id)

        # 2️⃣ VALIDATION
        if quotation.status != QuotationStatus.approved:
            raise HTTPException(
                status_code=409,
                detail="Only approved quotations can be converted to invoice",
            )
        
        if quotation.status == QuotationStatus.converted_to_invoice:
            raise HTTPException(
                status_code=409,
                detail="Once converted, quotation cannot be converted again",
            )

        if quotation.version != version:
            raise HTTPException(
                status_code=409,
                detail="Quotation modified by another process",
            )

        # 3️⃣ STATE TRANSITION
        quotation.status = QuotationStatus.converted_to_invoice
        quotation.version += 1
        quotation.updated_by_id = user.id

        await db.commit()

    except Exception:
        await db.rollback()
        raise

    # 4️⃣ FETCH FULL DATA (NO LOCK)
    quotation = await _get_quotation_with_items(db, quotation_id)

    # 5️⃣ ACTIVITY
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CONVERT_QUOTATION_TO_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
    )

    return QuotationResponse(
        message="Quotation converted to invoice successfully",
        data=_map_quotation(quotation),
    )
