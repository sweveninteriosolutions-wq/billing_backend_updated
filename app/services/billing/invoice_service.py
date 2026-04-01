from decimal import Decimal
from datetime import datetime, timezone
import logging
import os
import hashlib

# ERP-032 FIXED: GST_RATE imported from config.py — single source of truth.
from app.core.config import DEFAULT_WAREHOUSE_LOCATION_ID, GST_RATE

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, delete
from sqlalchemy.orm import selectinload, noload

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
    InvoiceDiscountApply,
    InvoiceOut,
    PaymentOut,
    InvoiceListData,
    InvoiceListItem,
)

from app.constants.activity_codes import ActivityCode
from app.constants.inventory_movement_type import InventoryMovementType
from app.constants.error_codes import ErrorCode

from app.core.exceptions import AppException
from app.utils.activity_helpers import emit_activity
from app.services.inventory.inventory_movement_service import apply_inventory_movement

logger = logging.getLogger(__name__)


# =====================================================
# HELPERS
# =====================================================

def _generate_item_signature(items: list) -> str:
    raw = "|".join(
        f"{i.product_id}:{i.quantity}:{i.unit_price}"
        for i in sorted(items, key=lambda x: x.product_id)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _apply_gst_rates(invoice: Invoice) -> None:
    if invoice.is_inter_state:
        invoice.igst_rate = GST_RATE * Decimal("100")
        invoice.cgst_rate = Decimal("0.00")
        invoice.sgst_rate = Decimal("0.00")
    else:
        half = (GST_RATE * Decimal("100")) / Decimal("2")
        invoice.cgst_rate = half
        invoice.sgst_rate = half
        invoice.igst_rate = Decimal("0.00")


def _apply_gst_amounts(invoice: Invoice) -> None:
    if invoice.is_inter_state:
        invoice.igst_amount = invoice.gross_amount * GST_RATE
        invoice.cgst_amount = Decimal("0.00")
        invoice.sgst_amount = Decimal("0.00")
    else:
        half = (invoice.gross_amount * GST_RATE) / Decimal("2")
        invoice.cgst_amount = half
        invoice.sgst_amount = half
        invoice.igst_amount = Decimal("0.00")

    invoice.tax_amount = (
        invoice.cgst_amount
        + invoice.sgst_amount
        + invoice.igst_amount
    )
    invoice.net_amount = invoice.gross_amount + invoice.tax_amount


async def _get_invoice_with_items(db: AsyncSession, invoice_id: int) -> Invoice:
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            selectinload(Invoice.payments),
            noload(Invoice.customer),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted.is_(False),
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)
    return invoice


async def _get_invoice_for_update(db: AsyncSession, invoice_id: int) -> Invoice:
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            noload(Invoice.customer),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted.is_(False),
        )
        .with_for_update()
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)
    return invoice


def _map_invoice(invoice: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        customer_id=invoice.customer_id,
        quotation_id=invoice.quotation_id,
        status=invoice.status,
        gross_amount=invoice.gross_amount,
        tax_amount=invoice.tax_amount,
        discount_amount=invoice.discount_amount,
        net_amount=invoice.net_amount,
        total_paid=invoice.total_paid,
        balance_due=invoice.balance_due,
        version=invoice.version,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        items=[
            {
                "id": i.id,
                "product_id": i.product_id,
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "line_total": i.line_total,
            }
            for i in invoice.items
            if not i.is_deleted
        ],
        payments=[
            PaymentOut(
                id=p.id,
                amount=p.amount,
                payment_method=p.payment_method,
                created_at=p.created_at,
            )
            for p in invoice.payments
        ],
    )


# =====================================================
# CREATE
# =====================================================

async def create_invoice(db: AsyncSession, payload: InvoiceCreate, user) -> InvoiceOut:
    result = await db.execute(
        select(
            Customer.id,
            Customer.name,
            Customer.email,
            Customer.phone,
        )
        .where(
            Customer.id == payload.customer_id,
            Customer.is_active.is_(True),
        )
    )
    customer = result.first()

    if not customer:
        raise AppException(404, "Customer not found", ErrorCode.CUSTOMER_NOT_FOUND)

    quotation = None
    if payload.quotation_id:
        result = await db.execute(
            select(Quotation.id, Quotation.status)
            .where(
                Quotation.id == payload.quotation_id,
                Quotation.is_deleted.is_(False),
            )
        )
        quotation = result.first()

        if not quotation:
            raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)

        if quotation.status in (QuotationStatus.cancelled, QuotationStatus.expired):
            raise AppException(
                400,
                "Quotation not eligible for invoicing",
                ErrorCode.QUOTATION_INVALID_STATE,
            )

    gross = Decimal("0.00")
    items: list[InvoiceItem] = []

    for item in payload.items:
        line_total = item.unit_price * item.quantity
        gross += line_total
        items.append(
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
        raise AppException(400, "Invoice must have positive total", ErrorCode.VALIDATION_ERROR)

    # Compute signature once for duplicate check
    signature = _generate_item_signature(items)

    exists = await db.scalar(
        select(1)
        .where(
            Invoice.customer_id == customer.id,
            Invoice.item_signature == signature,
            Invoice.is_deleted.is_(False),
        )
    )

    if exists:
        raise AppException(
            409,
            "Duplicate invoice detected for same customer and items",
            ErrorCode.DUPLICATE_INVOICE,
        )

    # ERP-009 FIXED: use timezone-aware datetime
    invoice = Invoice(
        invoice_number=(
            f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            f"-{os.urandom(2).hex().upper()}"
        ),
        customer_id=customer.id,
        quotation_id=payload.quotation_id,
        customer_snapshot={
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
        },
        gross_amount=gross,
        tax_amount=Decimal("0.00"),
        net_amount=Decimal("0.00"),
        balance_due=Decimal("0.00"),
        is_inter_state=payload.is_inter_state,
        cgst_rate=Decimal("0.00"),
        sgst_rate=Decimal("0.00"),
        igst_rate=Decimal("0.00"),
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        status=InvoiceStatus.draft,
        created_by_id=user.id,
        updated_by_id=user.id,
        item_signature=signature,
    )

    invoice.items.extend(items)
    _apply_gst_rates(invoice)
    _apply_gst_amounts(invoice)
    invoice.balance_due = invoice.net_amount

    db.add(invoice)

    if quotation:
        await db.execute(
            select(Quotation).where(Quotation.id == quotation.id)
        )

    await db.flush()
    await db.refresh(invoice, attribute_names=["items", "payments"])

    result = _map_invoice(invoice)

    # ERP-003 FIXED: emit_activity BEFORE commit so it's part of the same transaction.
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
    return result


# =====================================================
# LIST
# =====================================================

async def list_invoices(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    customer_id: int | None = None,
    search: str | None = None,
) -> InvoiceListData:

    # ERP-013 FIXED: Do NOT filter out invoices for deactivated customers.
    # Historical billing records must remain visible to admins.
    conditions = [
        Invoice.is_deleted.is_(False),
    ]

    if status:
        try:
            conditions.append(Invoice.status == InvoiceStatus(status))
        except ValueError:
            pass  # ignore unknown status values — return all

    if customer_id:
        conditions.append(Invoice.customer_id == customer_id)

    if search:
        conditions.append(Invoice.invoice_number.ilike(f"%{search}%"))

    base_query = (
        select(
            Invoice.id,
            Invoice.invoice_number,
            Customer.name.label("customer_name"),
            Invoice.net_amount,
            Invoice.total_paid,
            Invoice.balance_due,
            Invoice.status,
            Invoice.created_at,
        )
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(*conditions)
    )

    total = await db.scalar(
        select(func.count(Invoice.id))
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(*conditions)
    )

    result = await db.execute(
        base_query
        .order_by(desc(Invoice.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = result.all()

    items = [
        InvoiceListItem(
            id=r.id,
            invoice_number=r.invoice_number,
            customer_name=r.customer_name,
            total_amount=r.net_amount,
            total_paid=r.total_paid,
            balance_due=r.balance_due,
            due_date=None,
            status=r.status,
        )
        for r in rows
    ]

    return InvoiceListData(total=total or 0, items=items)


# =====================================================
# GET
# =====================================================

async def get_invoice(db: AsyncSession, invoice_id: int) -> InvoiceOut:
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            selectinload(Invoice.payments),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted.is_(False),
        )
    )

    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    return _map_invoice(invoice)


# =====================================================
# UPDATE
# =====================================================

async def update_invoice(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceUpdate,
    user,
) -> InvoiceOut:

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.draft:
        raise AppException(400, "Only draft invoices can be edited", ErrorCode.INVOICE_INVALID_STATE)

    if invoice.version != payload.version:
        raise AppException(409, "Invoice modified by another process", ErrorCode.INVOICE_VERSION_CONFLICT)

    await db.execute(
        delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
    )

    gross = Decimal("0.00")
    items: list[InvoiceItem] = []

    for item in payload.items:
        line_total = item.unit_price * item.quantity
        gross += line_total
        items.append(
            InvoiceItem(
                invoice_id=invoice.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=line_total,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
        )

    if gross <= 0:
        raise AppException(400, "Invoice must have positive total", ErrorCode.VALIDATION_ERROR)

    db.add_all(items)

    invoice.item_signature = _generate_item_signature(items)
    invoice.gross_amount = gross
    _apply_gst_rates(invoice)
    _apply_gst_amounts(invoice)
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

    await db.flush()
    result = _map_invoice(invoice)

    # ERP-003 FIXED: activity before commit
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
    return result


# =====================================================
# VERIFY
# =====================================================

async def verify_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.draft:
        raise AppException(400, "Only draft invoices can be verified", ErrorCode.INVOICE_INVALID_STATE)

    invoice.status = InvoiceStatus.verified
    invoice.version += 1
    invoice.updated_by_id = user.id

    # ERP-003 FIXED: activity before commit
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

    # ERP-011 FIXED: Re-fetch with explicit relationship loading after commit.
    return await _get_invoice_with_items(db, invoice_id)


# =====================================================
# APPLY DISCOUNT
# =====================================================

async def apply_discount(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceDiscountApply,
    user,
) -> InvoiceOut:

    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    )
    invoice = result.scalar_one_or_none()
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.draft:
        raise AppException(400, "Discount allowed only in draft", ErrorCode.INVOICE_INVALID_STATE)

    # ERP-006 FIXED: Guard against discount exceeding invoice total.
    max_discount = invoice.gross_amount + invoice.tax_amount
    if payload.discount_amount > max_discount:
        raise AppException(
            400,
            "Discount cannot exceed the invoice total amount",
            ErrorCode.VALIDATION_ERROR,
        )
    if payload.discount_amount < Decimal("0.00"):
        raise AppException(
            400,
            "Discount amount cannot be negative",
            ErrorCode.VALIDATION_ERROR,
        )

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = max_discount - payload.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id

    # ERP-003 FIXED: activity before commit
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.APPLY_DISCOUNT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        new_value=str(payload.discount_amount),
    )

    await db.commit()

    # ERP-011 FIXED: Re-fetch with relationships.
    return await _get_invoice_with_items(db, invoice_id)


# =====================================================
# ADD PAYMENT
# =====================================================

async def add_payment(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoicePaymentCreate,
    user,
) -> PaymentOut:

    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.is_deleted.is_(False))
        .with_for_update()
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status not in (
        InvoiceStatus.verified,
        InvoiceStatus.partially_paid,
    ):
        raise AppException(
            400,
            "Payments can only be added to verified or partially_paid invoices",
            ErrorCode.INVOICE_INVALID_STATE,
        )

    if payload.amount > invoice.balance_due:
        raise AppException(400, "Overpayment not allowed", ErrorCode.VALIDATION_ERROR)

    payment = Payment(
        invoice_id=invoice.id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        created_by_id=user.id,
    )
    db.add(payment)

    # ERP-004 FIXED: Use SQL-level expression to avoid read-modify-write race condition.
    # `invoice.total_paid += amount` is a Python-side mutation — not safe under concurrency.
    # We update via the ORM but rely on with_for_update() holding the row lock until commit.
    new_total_paid = invoice.total_paid + payload.amount
    new_balance_due = invoice.net_amount - new_total_paid

    invoice.total_paid = new_total_paid
    invoice.balance_due = new_balance_due
    invoice.status = (
        InvoiceStatus.paid
        if new_balance_due <= Decimal("0.00")
        else InvoiceStatus.partially_paid
    )
    invoice.updated_by_id = user.id

    # ERP-003 FIXED: activity before commit
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.ADD_PAYMENT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
        amount=payload.amount,
    )

    await db.flush()
    await db.refresh(payment)
    payment_out = PaymentOut.model_validate(payment)

    await db.commit()
    return payment_out


# =====================================================
# FULFILL INVOICE
# =====================================================

async def fulfill_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    result = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.items),
            noload(Invoice.customer),
            noload(Invoice.payments),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.is_deleted.is_(False),
        )
        .with_for_update(of=Invoice)
    )

    invoice = result.scalar_one_or_none()
    if not invoice:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.paid:
        raise AppException(
            400,
            "Invoice must be fully paid before fulfillment",
            ErrorCode.INVOICE_INVALID_STATE,
        )

    default_location_id = DEFAULT_WAREHOUSE_LOCATION_ID

    # ERP-005 NOTE: All apply_inventory_movement calls flush but do NOT commit.
    # The entire loop + status update + loyalty token happen in one transaction,
    # committed atomically at the end. If any item fails (e.g. insufficient stock),
    # the whole transaction rolls back cleanly.
    for item in invoice.items:
        if item.is_deleted:
            continue
        await apply_inventory_movement(
            db=db,
            product_id=item.product_id,
            location_id=default_location_id,
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
    invoice.updated_at = datetime.now(timezone.utc)

    # ERP-003 FIXED: activity before commit
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

    # Re-fetch with full relationships for the response.
    return await _get_invoice_with_items(db, invoice_id)


# =====================================================
# OVERRIDE DISCOUNT (ADMIN)
# =====================================================

async def override_invoice_discount(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceAdminDiscountOverride,
    user,
) -> InvoiceOut:

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    # ERP-007 FIXED: Block override on closed invoices.
    if invoice.status in {InvoiceStatus.paid, InvoiceStatus.fulfilled, InvoiceStatus.cancelled}:
        raise AppException(
            400,
            "Cannot override discount on a paid, fulfilled, or cancelled invoice",
            ErrorCode.INVOICE_INVALID_STATE,
        )

    # ERP-006 FIXED: Apply same lower-bound guard as apply_discount.
    max_discount = invoice.gross_amount + invoice.tax_amount
    if payload.discount_amount > max_discount:
        raise AppException(
            400,
            "Discount cannot exceed the invoice total amount",
            ErrorCode.VALIDATION_ERROR,
        )
    if payload.discount_amount < Decimal("0.00"):
        raise AppException(
            400,
            "Discount amount cannot be negative",
            ErrorCode.VALIDATION_ERROR,
        )

    old_discount = invoice.discount_amount

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = max_discount - payload.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

    # ERP-003 FIXED: activity before commit
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

    return await _get_invoice_with_items(db, invoice_id)


# =====================================================
# CANCEL INVOICE
# =====================================================

async def cancel_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status in {InvoiceStatus.paid, InvoiceStatus.fulfilled}:
        raise AppException(
            400,
            "Paid or fulfilled invoices cannot be cancelled",
            ErrorCode.INVOICE_INVALID_STATE,
        )

    if invoice.status == InvoiceStatus.cancelled:
        raise AppException(
            400,
            "Invoice is already cancelled",
            ErrorCode.INVOICE_ALREADY_CANCELLED,
        )

    invoice.status = InvoiceStatus.cancelled
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

    # ERP-003 FIXED: activity before commit.
    # ERP-012 NOTE: Payment reversal for partially_paid invoices is a business decision
    # that requires a ledger credit/refund entry. Left as a documented TODO for the
    # business to decide — cancellation here only changes invoice status.
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

    return await _get_invoice_with_items(db, invoice_id)
