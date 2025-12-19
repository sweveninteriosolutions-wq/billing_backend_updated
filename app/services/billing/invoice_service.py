from decimal import Decimal
from datetime import datetime, timezone
import logging
import os
import hashlib

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

GST_RATE = Decimal(os.getenv("GST_RATE", "0.18"))

def _generate_item_signature(items: list[InvoiceItem]) -> str:
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


async def create_invoice(db: AsyncSession, payload: InvoiceCreate, user) -> InvoiceOut:
    customer = await db.get(Customer, payload.customer_id)
    if not customer or not customer.is_active:
        raise AppException(404, "Customer not found", ErrorCode.CUSTOMER_NOT_FOUND)

    quotation = None
    if payload.quotation_id:
        quotation = await db.get(Quotation, payload.quotation_id)
        if not quotation or quotation.is_deleted:
            raise AppException(404, "Quotation not found", ErrorCode.QUOTATION_NOT_FOUND)

        if quotation.status in {
            QuotationStatus.cancelled,
            QuotationStatus.expired,
        }:
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

    invoice = Invoice(
        invoice_number=f"INV-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
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
    )

    invoice.items.extend(items)
    _apply_gst_rates(invoice)
    _apply_gst_amounts(invoice)
    invoice.balance_due = invoice.net_amount
    invoice.item_signature = _generate_item_signature(invoice.items)

    db.add(invoice)

    if quotation:
        quotation.status = QuotationStatus.invoiced
        quotation.updated_by_id = user.id

    await db.flush()
    await db.refresh(invoice, attribute_names=["items", "payments"])

    result = _map_invoice(invoice)
    await db.commit()

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_INVOICE,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=invoice.invoice_number,
    )

    return result


async def list_invoices(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> InvoiceListData:

    base_query = (
        select(
            Invoice.id,
            Invoice.invoice_number,
            Customer.name.label("customer_name"),
            Invoice.net_amount,
            Invoice.total_paid,
            Invoice.balance_due,
            Invoice.status,
        )
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(
            Invoice.is_deleted.is_(False),
            Customer.is_active.is_(True),
        )
    )

    total = await db.scalar(
        select(func.count(Invoice.id))
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(
            Invoice.is_deleted.is_(False),
            Customer.is_active.is_(True),
        )
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

    invoice.item_signature = _generate_item_signature(invoice.items)

    db.add_all(items)

    invoice.gross_amount = gross
    _apply_gst_rates(invoice)
    _apply_gst_amounts(invoice)

    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

    await db.flush()
    result = _map_invoice(invoice)
    await db.commit()

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

    return result


async def verify_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.draft:
        raise AppException(400, "Only draft invoices can be verified", ErrorCode.INVOICE_INVALID_STATE)

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
    await db.refresh(invoice)
    return _map_invoice(invoice)


async def apply_discount(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceDiscountApply,
    user,
) -> InvoiceOut:

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status != InvoiceStatus.draft:
        raise AppException(400, "Discount allowed only in draft", ErrorCode.INVOICE_INVALID_STATE)

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = invoice.gross_amount + invoice.tax_amount - payload.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id

    await db.commit()
    await db.refresh(invoice)
    return _map_invoice(invoice)



async def add_payment(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoicePaymentCreate,
    user,
) -> PaymentOut:

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if payload.amount > invoice.balance_due:
        raise AppException(400, "Overpayment not allowed", ErrorCode.VALIDATION_ERROR)

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
    return PaymentOut.model_validate(payment)


async def fulfill_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    result = await db.execute(
        select(Invoice)
        .options(noload("*"))
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
    invoice.updated_at = datetime.now(timezone.utc)

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
    return _map_invoice(invoice)


async def override_invoice_discount(
    db: AsyncSession,
    invoice_id: int,
    payload: InvoiceAdminDiscountOverride,
    user,
) -> InvoiceOut:

    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    old_discount = invoice.discount_amount

    invoice.discount_amount = payload.discount_amount
    invoice.net_amount = invoice.gross_amount + invoice.tax_amount - payload.discount_amount
    invoice.balance_due = invoice.net_amount - invoice.total_paid
    invoice.version += 1
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

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
    return _map_invoice(invoice)


async def cancel_invoice(db: AsyncSession, invoice_id: int, user) -> InvoiceOut:
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.is_deleted:
        raise AppException(404, "Invoice not found", ErrorCode.INVOICE_NOT_FOUND)

    if invoice.status in {
        InvoiceStatus.paid,
        InvoiceStatus.fulfilled,
    }:
        raise AppException(
            400,
            "Paid or fulfilled invoices cannot be cancelled",
            ErrorCode.INVOICE_INVALID_STATE,
        )

    invoice.status = InvoiceStatus.cancelled
    invoice.updated_by_id = user.id
    invoice.updated_at = datetime.now(timezone.utc)

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
    return _map_invoice(invoice)
