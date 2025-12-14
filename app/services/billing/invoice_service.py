from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import (
    noload,
    selectinload,
)
from fastapi import HTTPException
from decimal import Decimal
from uuid import uuid4

from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.billing.payment_models import Payment
from app.models.billing.loyaltyTokens_models import LoyaltyToken
from app.models.billing.quotation_models import Quotation

from app.models.enums.invoice_status import InvoiceStatus
from app.models.enums.quotation_status import QuotationStatus

from app.schemas.billing.invoice_schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceAdminDiscountOverride,
    InvoicePaymentCreate,
    InvoiceResponse,
    InvoiceOut,
    PaymentResponse,
)

from app.constants.activity_codes import ActivityCode
from app.constants.inventory_movement_type import InventoryMovementType

from app.utils.activity_helpers import emit_activity
from app.services.inventory.inventory_movement_service import apply_inventory_movement


# =====================================================
# CREATE INVOICE
# =====================================================
async def create_invoice(
    db: AsyncSession,
    payload: InvoiceCreate,
    user,
):
    # -------------------------------------------------
    # 1. Validate & lock quotation (if provided)
    # -------------------------------------------------
    quotation = None

    if payload.quotation_id:
        result = await db.execute(
            select(Quotation)
            .options(noload("*"))
            .where(
                Quotation.id == payload.quotation_id,
                Quotation.is_deleted == False,
            )
            .with_for_update(of=Quotation)
        )
        quotation = result.scalar_one_or_none()

        if not quotation:
            raise HTTPException(404, "Quotation not found")

        if quotation.status in {
            QuotationStatus.cancelled,
            QuotationStatus.expired,
        }:
            raise HTTPException(
                400,
                f"Cannot invoice quotation in {quotation.status} state",
            )

    # -------------------------------------------------
    # 2. Create invoice
    # -------------------------------------------------
    invoice = Invoice(
        invoice_number=f"INV-{uuid4().hex[:10].upper()}",
        customer_id=payload.customer_id,
        quotation_id=payload.quotation_id,
        customer_snapshot={},
        status=InvoiceStatus.draft,
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    gross = Decimal("0.00")

    for item in payload.items:
        line_total = item.unit_price * item.quantity
        gross += line_total

        invoice.items.append(
            InvoiceItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )

    invoice.gross_amount = gross
    invoice.net_amount = gross
    invoice.balance_due = gross

    db.add(invoice)

    # -------------------------------------------------
    # 3. Update quotation status → INVOICED
    # -------------------------------------------------
    if quotation:
        quotation.status = QuotationStatus.invoiced
        quotation.updated_by_id = user.id

    # -------------------------------------------------
    # 4. Commit ONCE
    # -------------------------------------------------
    await db.commit()

    # -------------------------------------------------
    # 5. Activity log
    # -------------------------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    # -------------------------------------------------
    # 6. Refresh for response safety
    # -------------------------------------------------
    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Invoice created",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# VERIFY INVOICE
# =====================================================
async def verify_invoice(
    db: AsyncSession,
    invoice_id: int,
    user,
):
    invoice = await db.get(Invoice, invoice_id)

    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(400, "Only draft invoices can be verified")

    invoice.status = InvoiceStatus.verified
    invoice.version += 1
    invoice.updated_by_id = user.id

    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.VERIFY_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Invoice verified",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# APPLY DISCOUNT (DRAFT ONLY)
# =====================================================
async def apply_discount(
    db: AsyncSession,
    invoice_id: int,
    payload,
    user,
):
    invoice = await db.get(Invoice, invoice_id)

    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(400, "Discount allowed only in draft")

    old_discount = invoice.discount_amount

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = invoice.gross_amount - payload.discount_amount
    invoice.balance_due = invoice.net_amount
    invoice.version += 1
    invoice.updated_by_id = user.id

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.APPLY_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        old_value=str(old_discount),
        new_value=str(payload.discount_amount),
    )

    return InvoiceResponse(
        message="Discount applied",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# ADD PAYMENT (LOCKED)
# =====================================================
async def add_payment(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoicePaymentCreate,
    user,
):
    result = await db.execute(
        select(Invoice)
        .options(noload("*"))
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted == False,
        )
        .with_for_update(of=Invoice)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    if payload.amount > invoice.balance_due:
        raise HTTPException(400, "Overpayment not allowed")

    payment = Payment(
        invoice_id=invoice.id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        created_by_id=user.id,
    )
    db.add(payment)

    invoice.total_paid += payload.amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid

    invoice.status = (
        InvoiceStatus.paid
        if invoice.balance_due <= Decimal("0.00")
        else InvoiceStatus.partially_paid
    )
    invoice.updated_by_id = user.id

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(payment)

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=(
            ActivityCode.MARK_PAID
            if invoice.status == InvoiceStatus.paid
            else ActivityCode.PARTIAL_PAYMENT
        ),
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        amount=str(payload.amount),
    )

    return PaymentResponse(
        message="Payment recorded",
        data=payment,
    )


# =====================================================
# FULFILL INVOICE
# =====================================================
async def fulfill_invoice(
    db: AsyncSession,
    invoice_id: int,
    user,
):
    result = await db.execute(
        select(Invoice)
        .options(noload("*"))
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted == False,
        )
        .with_for_update(of=Invoice)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.paid:
        raise HTTPException(400, "Invoice must be fully paid")

    await db.refresh(invoice, attribute_names=["items"])

    if not invoice.items:
        raise HTTPException(400, "Invoice has no items")

    for item in invoice.items:
        await apply_inventory_movement(
            db=db,
            product_id=item.product_id,
            location_id=1,
            quantity_change=-item.quantity,
            movement_type=InventoryMovementType.STOCK_OUT,
            reference_type="INVOICE",
            reference_id=invoice.id,
            actor_user=user,
        )

    tokens = int(invoice.net_amount // Decimal("1000"))
    if tokens > 0:
        db.add(
            LoyaltyToken(
                customer_id=invoice.customer_id,
                invoice_id=invoice.id,
                tokens=tokens,
                created_by_id=user.id,
            )
        )

    invoice.status = InvoiceStatus.fulfilled
    invoice.updated_by_id = user.id

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.FULFILL_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    return InvoiceResponse(
        message="Invoice fulfilled",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# GET INVOICE
# =====================================================
async def get_invoice(
    db: AsyncSession,
    invoice_id: int,
):
    invoice = await db.get(Invoice, invoice_id)

    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    return InvoiceResponse(
        message="Invoice retrieved",
        data=invoice,
    )


# =====================================================
# LIST INVOICES
# =====================================================
async def list_invoices(db: AsyncSession):
    result = await db.execute(
        select(Invoice)
        .where(Invoice.is_deleted == False)
        .order_by(Invoice.created_at.desc())
    )
    return result.scalars().all()


# =====================================================
# UPDATE INVOICE
# =====================================================
async def update_invoice(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceUpdate,
    user,
):
    invoice = await db.get(Invoice, invoice_id)

    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(400, "Only draft invoices can be edited")

    if invoice.version != payload.version:
        raise HTTPException(409, "Invoice modified by another process")

    for item in invoice.items:
        item.is_deleted = True

    invoice.items.clear()

    gross = Decimal("0.00")

    for item in payload.items:
        line_total = item.quantity * item.unit_price
        gross += line_total

        invoice.items.append(
            InvoiceItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )

    invoice.gross_amount = gross
    invoice.net_amount = gross - invoice.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        changes="items",
    )

    return InvoiceResponse(
        message="Invoice updated",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# OVERRIDE DISCOUNT
# =====================================================
async def override_invoice_discount(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceAdminDiscountOverride,
    user,
):
    result = await db.execute(
        select(Invoice)
        .options(noload("*"))
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted == False,
        )
        .with_for_update(of=Invoice)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.verified:
        raise HTTPException(400, "Override allowed only on verified invoices")

    if invoice.total_paid > 0:
        raise HTTPException(400, "Cannot override after payment started")

    if payload.version != invoice.version:
        raise HTTPException(409, "Invoice modified by another process")

    if payload.discount_amount > invoice.gross_amount:
        raise HTTPException(400, "Discount exceeds gross amount")

    old_discount = invoice.discount_amount

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = invoice.gross_amount - payload.discount_amount
    invoice.balance_due = invoice.net_amount
    invoice.version += 1
    invoice.updated_by_id = user.id

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.OVERRIDE_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        old_value=str(old_discount),
        new_value=str(payload.discount_amount),
    )

    return InvoiceResponse(
        message="Discount overridden",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# CANCEL INVOICE
# =====================================================
async def cancel_invoice(
    db: AsyncSession,
    invoice_id: int,
    user,
):
    invoice = await db.get(Invoice, invoice_id)

    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status in {
        InvoiceStatus.paid,
        InvoiceStatus.fulfilled,
    }:
        raise HTTPException(
            400,
            "Cannot cancel paid or fulfilled invoice",
        )

    invoice.status = InvoiceStatus.cancelled
    invoice.updated_by_id = user.id

    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CANCEL_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    return InvoiceResponse(
        "Invoice cancelled",
        invoice,
    )
