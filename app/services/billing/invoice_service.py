from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import noload, selectinload
from fastapi import HTTPException
from decimal import Decimal
from uuid import uuid4

from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.billing.payment_models import Payment
from app.models.billing.loyaltyTokens_models import LoyaltyToken
from app.models.billing.quotation_models import Quotation
from app.models.masters.customer_models import Customer

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
    InvoiceListResponse,
)

from app.constants.activity_codes import ActivityCode
from app.constants.inventory_movement_type import InventoryMovementType

from app.utils.activity_helpers import emit_activity
from app.services.inventory.inventory_movement_service import apply_inventory_movement


# =====================================================
# CREATE INVOICE
# =====================================================
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import noload
from fastapi import HTTPException

from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.billing.quotation_models import Quotation
from app.models.masters.customer_models import Customer
from app.models.enums.invoice_status import InvoiceStatus
from app.models.enums.quotation_status import QuotationStatus
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity

GST_RATE = Decimal("0.18")  # move to env if needed

async def create_invoice(db: AsyncSession, payload: InvoiceCreate, user):

    # ----------------------------------
    # 1. Validate customer & snapshot
    # ----------------------------------
    result = await db.execute(
        select(Customer)
        .options(noload("*"))   # 🔥 THIS IS THE FIX
        .where(
            Customer.id == payload.customer_id,
            Customer.is_active.is_(True),
        )
    )
    customer = result.scalar_one_or_none()
    if not customer or not customer.is_active:
        raise HTTPException(404, "Customer not found or inactive")

    # ----------------------------------
    # 2. Validate & lock quotation (OPTIONAL, SAFE)
    # ----------------------------------
    quotation = None
    if payload.quotation_id:
        try:
            result = await db.execute(
                select(Quotation)
                .options(noload("*"))
                .where(
                    Quotation.id == payload.quotation_id,
                    Quotation.is_deleted.is_(False),
                )
                .with_for_update(nowait=True)
            )
        except Exception:
            raise HTTPException(
                status_code=409,
                detail="Quotation is being processed by another request",
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

    # ----------------------------------
    # 3. Build items + gross
    # ----------------------------------
    gross = Decimal("0.00")
    invoice_items: list[InvoiceItem] = []

    for item in payload.items:
        line_total = item.unit_price * item.quantity
        gross += line_total

        invoice_items.append(
            InvoiceItem(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )

    if gross <= 0:
        raise HTTPException(400, "Invoice total must be greater than zero")

    # ----------------------------------
    # 4. TAX — ALWAYS FROM GROSS (MANUAL INVOICE)
    # ----------------------------------
    tax_amount = (gross * GST_RATE).quantize(Decimal("0.01"))
    net_amount = gross + tax_amount

    # ----------------------------------
    # 5. Create invoice (SOURCE OF TRUTH)
    # ----------------------------------
    invoice = Invoice(
        invoice_number=f"INV-{uuid4().hex[:10].upper()}",
        customer_id=customer.id,
        quotation_id=payload.quotation_id,
        customer_snapshot={
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
        },
        gross_amount=gross,
        tax_amount=tax_amount,
        net_amount=net_amount,
        balance_due=net_amount,
        status=InvoiceStatus.draft,
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    invoice.items.extend(invoice_items)
    db.add(invoice)

    # ----------------------------------
    # 6. Mark quotation invoiced
    # ----------------------------------
    if quotation:
        quotation.status = QuotationStatus.invoiced
        quotation.updated_by_id = user.id

    # ----------------------------------
    # 7. COMMIT (FAST)
    # ----------------------------------
    # await db.commit()
    # await db.refresh(invoice)

    # ----------------------------------
    # 8. Activity log (POST-COMMIT)
    # ----------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    await db.commit()

    await db.refresh(invoice)
    return InvoiceResponse(
        message="Invoice created",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# VERIFY INVOICE
# =====================================================
async def verify_invoice(db: AsyncSession, invoice_id: int, user):

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(400, "Only draft invoices can be verified")

    invoice.status = InvoiceStatus.verified
    invoice.version += 1
    invoice.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.VERIFY_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    await db.commit()
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Invoice verified",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# APPLY DISCOUNT
# =====================================================
async def apply_discount(db: AsyncSession, invoice_id: int, payload, user):

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

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Discount applied",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# ADD PAYMENT
# =====================================================
async def add_payment(db: AsyncSession, invoice_id: int, payload: InvoicePaymentCreate, user):

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

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(payment)

    return PaymentResponse(
        message="Payment recorded",
        data=payment,
    )


# =====================================================
# FULFILL INVOICE (ATOMIC)
# =====================================================
async def fulfill_invoice(db: AsyncSession, invoice_id: int, user):

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

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.FULFILL_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Invoice fulfilled",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# GET INVOICE
# =====================================================
async def get_invoice(db: AsyncSession, invoice_id: int):

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    return InvoiceResponse(
        message="Invoice retrieved",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# UPDATE INVOICE
# =====================================================
async def update_invoice(db: AsyncSession, invoice_id: int, payload: InvoiceUpdate, user):

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

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Invoice updated",
        data=InvoiceOut.model_validate(invoice),
    )


# =====================================================
# CANCEL INVOICE
# =====================================================
async def cancel_invoice(db: AsyncSession, invoice_id: int, user):

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    if invoice.status in {InvoiceStatus.paid, InvoiceStatus.fulfilled}:
        raise HTTPException(400, "Cannot cancel paid or fulfilled invoice")

    invoice.status = InvoiceStatus.cancelled
    invoice.updated_by_id = user.id

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CANCEL_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    await db.commit()

    return InvoiceResponse(
        message="Invoice cancelled",
        data=InvoiceOut.model_validate(invoice),
    )

# =====================================================
# LIST INVOICES WITH PAGINATION
# =====================================================
async def list_invoices(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    include_total: bool = False,  # 🔥 IMPORTANT
):
    base_query = (
        select(Invoice)
        .where(Invoice.is_deleted == False)
        .order_by(Invoice.created_at.desc())
    )

    total = None
    if include_total:
        total = await db.scalar(
            select(func.count()).select_from(
                select(Invoice.id)
                .where(Invoice.is_deleted == False)
                .subquery()
            )
        )

    result = await db.execute(
        base_query
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    invoices = result.scalars().all()

    return {
        "message": "Invoices retrieved",
        "page": page,
        "page_size": page_size,
        "total": total,   # None if skipped
        "data": invoices,
    }


# =====================================================
# OVERRIDE DISCOUNT (ADMIN)
# =====================================================
async def override_invoice_discount(db: AsyncSession, invoice_id: int, payload: InvoiceAdminDiscountOverride, user):

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise HTTPException(404, "Invoice not found")

    old_discount = invoice.discount_amount

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = invoice.gross_amount - payload.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id

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
        reason=payload.reason,
    )

    await db.commit()

    await db.refresh(invoice)
    await db.refresh(invoice, attribute_names=["items", "payments"])

    return InvoiceResponse(
        message="Discount overridden by admin",
        data=InvoiceOut.model_validate(invoice),
    )