from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

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
from app.constants.activity_codes import ActivityCode
import hashlib

def generate_item_signature(items: list[tuple[int, int]]) -> str:
    """
    items = [(product_id, quantity), ...]
    Order-independent
    """
    normalized = sorted(f"{pid}:{qty}" for pid, qty in items)
    raw = "|".join(normalized)
    return hashlib.sha256(raw.encode()).hexdigest()


GST_RATE = Decimal("0.18")


# =====================================================
# INTERNAL HELPERS
# =====================================================

async def _get_quotation_with_items(
    db: AsyncSession,
    quotation_id: int,
) -> Quotation:
    result = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.items))
        .where(
            Quotation.id == quotation_id,
            Quotation.is_deleted == False,
        )
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(404, "Quotation not found")
    return quotation


async def recalculate_totals(quotation: Quotation):
    subtotal = Decimal("0.00")
    for item in quotation.items:
        if not item.is_deleted:
            subtotal += item.line_total

    quotation.subtotal_amount = subtotal
    quotation.tax_amount = subtotal * GST_RATE
    quotation.total_amount = subtotal + quotation.tax_amount


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
# CREATE QUOTATION (DEDUP BY ITEM SIGNATURE)
# =====================================================

async def create_quotation(
    db: AsyncSession,
    payload: QuotationCreate,
    user,
) -> QuotationResponse:

    # -------------------------------------------------
    # 1. Validate customer
    # -------------------------------------------------
    customer = await db.get(Customer, payload.customer_id)
    if not customer or not customer.is_active:
        raise HTTPException(status_code=404, detail="Customer not found")

    # -------------------------------------------------
    # 2. Build item signature (ONCE)
    # -------------------------------------------------
    items_for_signature = [
        (item.product_id, item.quantity)
        for item in payload.items
    ]

    signature = generate_item_signature(items_for_signature)

    # -------------------------------------------------
    # 3. Prevent duplicate DRAFT with same items
    # -------------------------------------------------
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
            detail=(
                "A draft quotation with the same items already exists. "
                "Please update the existing quotation instead."
            ),
        )

    # -------------------------------------------------
    # 4. Create quotation
    # -------------------------------------------------
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

    # -------------------------------------------------
    # 5. Create quotation items
    # -------------------------------------------------
    for item in payload.items:
        product = await db.get(Product, item.product_id)
        if not product or product.is_deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Invalid product {item.product_id}",
            )

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

    # -------------------------------------------------
    # 6. Recalculate totals
    # -------------------------------------------------
    quotation = await _get_quotation_with_items(db, quotation.id)
    await recalculate_totals(quotation)

    # -------------------------------------------------
    # 7. Commit
    # -------------------------------------------------
    await db.commit()

    # -------------------------------------------------
    # 8. Re-fetch AFTER commit (async-safe)
    # -------------------------------------------------
    quotation = await _get_quotation_with_items(db, quotation.id)

    # -------------------------------------------------
    # 9. Activity log
    # -------------------------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_QUOTATION,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=quotation.quotation_number,
    )

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

    return QuotationResponse(
        message="Quotation retrieved successfully",
        data=_map_quotation(quotation),
    )


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

    # -------------------------------------------------
    # UPDATE ITEMS (DRAFT ONLY)
    # -------------------------------------------------
    if payload.items is not None:
        # soft delete old items
        for old_item in quotation.items:
            old_item.is_deleted = True

        # add new items — IMPORTANT: append to relationship
        for item in payload.items:
            product = await db.get(Product, item.product_id)
            if not product or product.is_deleted :
                raise HTTPException(
                    status_code=404,
                    detail=f"Invalid product {item.product_id}",
                )

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

        # recompute item signature
        items_for_signature = [
            (item.product_id, item.quantity)
            for item in payload.items
        ]
        quotation.item_signature = generate_item_signature(items_for_signature)

        changes.append("items")

    # -------------------------------------------------
    # UPDATE META FIELDS
    # -------------------------------------------------
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

    # -------------------------------------------------
    # RECALCULATE TOTALS (NOW WORKS)
    # -------------------------------------------------
    await db.flush()
    await recalculate_totals(quotation)
    await db.commit()

    # -------------------------------------------------
    # RE-FETCH (ASYNC SAFE)
    # -------------------------------------------------
    quotation = await _get_quotation_with_items(db, quotation.id)

    # -------------------------------------------------
    # ACTIVITY LOG (SAFE)
    # -------------------------------------------------
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

    return QuotationResponse(
        message="Quotation updated successfully",
        data=_map_quotation(quotation),
    )


# =====================================================
# APPROVE (DRAFT → APPROVED)
# =====================================================

async def approve_quotation(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationResponse:

    # Atomic state transition
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
        raise HTTPException(
            status_code=409,
            detail="Quotation cannot be approved (already approved or modified)",
        )

    await db.commit()

    # 🔒 Re-fetch AFTER commit (prevents MissingGreenlet)
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

    return QuotationResponse(
        message="Quotation approved successfully",
        data=_map_quotation(quotation),
    )


# =====================================================
# DELETE QUOTATION (DRAFT ONLY)
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
        raise HTTPException(
            status_code=409,
            detail="Only draft quotations can be deleted or quotation was modified",
        )

    await db.commit()

    # 🔒 Re-fetch AFTER commit (async-safe)
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

    return QuotationResponse(
        message="Quotation deleted successfully",
        data=_map_quotation(quotation),
    )


async def convert_quotation_to_invoice(
    db: AsyncSession,
    quotation_id: int,
    version: int,
    user,
) -> QuotationResponse:

    # -------------------------------------------------
    # 1. Lock + validate quotation
    # -------------------------------------------------
    quotation = await _get_quotation_with_items(db, quotation_id)

    if quotation.status != QuotationStatus.approved:
        raise HTTPException(
            status_code=409,
            detail="Only approved quotations can be converted to invoice",
        )

    if quotation.version != version:
        raise HTTPException(
            status_code=409,
            detail="Quotation modified by another process",
        )

    try:
        # -------------------------------------------------
        # 2. Update quotation status (IN SAME TX)
        # -------------------------------------------------
        quotation.status = QuotationStatus.converted_to_invoice
        quotation.version += 1
        quotation.updated_by_id = user.id

        # -------------------------------------------------
        # 3. CREATE INVOICE HERE (NEXT STEP)
        # -------------------------------------------------
        # invoice = await create_invoice_from_quotation(db, quotation, user)
        # quotation.invoice_id = invoice.id

        await db.flush()

        # -------------------------------------------------
        # 4. Commit everything together
        # -------------------------------------------------
        await db.commit()

    except Exception:
        await db.rollback()
        raise

    # -------------------------------------------------
    # 5. Re-fetch safely
    # -------------------------------------------------
    quotation = await _get_quotation_with_items(db, quotation.id)

    # -------------------------------------------------
    # 6. Activity log
    # -------------------------------------------------
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
