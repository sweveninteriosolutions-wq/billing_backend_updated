# tests/test_invoice_service.py
#
# Covers: create_invoice, get_invoice, list_invoices, update_invoice,
#         verify_invoice, apply_discount, add_payment, cancel_invoice,
#         fulfill_invoice (mocked inventory movement)
#
# Design notes:
# - apply_inventory_movement uses WITH FOR UPDATE and inventory balance rows.
#   For fulfill_invoice we mock it out to isolate the invoice state machine.
# - Payment race condition: tested via sequential calls — no true concurrency
#   needed at unit test level (the DB-level guard is tested implicitly via rowcount).

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from tests.conftest import seed_user, StubUser
from app.services.billing import invoice_service
from app.services.masters import customer_service, product_service
from app.schemas.billing.invoice_schemas import (
    InvoiceCreate,
    InvoiceItemCreate,
    InvoiceUpdate,
    InvoiceItemUpdate,
    InvoiceDiscountApply,
    InvoicePaymentCreate,
)
from app.schemas.masters.customer_schema import CustomerCreate
from app.schemas.masters.product_schemas import ProductCreate
from app.models.enums.invoice_status import InvoiceStatus
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_customer(db, admin, email="inv_cust@test.com"):
    payload = CustomerCreate(name="InvCust", email=email, phone="8888888888")
    return await customer_service.create_customer(db, payload, admin)


async def _make_product(db, admin, sku="INV-PROD-001", price=1000, name=None):
    payload = ProductCreate(
        sku=sku,
        name=name or f"Product {sku}",
        hsn_code=9401,
        category="furniture",
        price=Decimal(str(price)),
        min_stock_threshold=0,
    )
    return await product_service.create_product(db, payload, admin)


async def _make_invoice(db, admin, customer_id, product_id, unit_price=1000, qty=1):
    payload = InvoiceCreate(
        customer_id=customer_id,
        is_inter_state=False,
        items=[InvoiceItemCreate(product_id=product_id, quantity=qty, unit_price=Decimal(str(unit_price)))],
    )
    return await invoice_service.create_invoice(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_invoice_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin)

    inv = await _make_invoice(db, admin, cust.id, prod.id)

    assert inv.id is not None
    assert inv.invoice_number.startswith("INV-")
    assert inv.status == InvoiceStatus.draft
    assert inv.gross_amount == Decimal("1000")
    assert inv.tax_amount > 0
    assert inv.net_amount == inv.gross_amount + inv.tax_amount
    assert len(inv.items) == 1


@pytest.mark.asyncio
async def test_create_invoice_invalid_customer_raises(db):
    admin = await _setup(db)
    prod = await _make_product(db, admin, sku="INV-NOCUST")

    payload = InvoiceCreate(
        customer_id=99999,
        is_inter_state=False,
        items=[InvoiceItemCreate(product_id=prod.id, quantity=1, unit_price=Decimal("500"))],
    )
    with pytest.raises(AppException) as exc:
        await invoice_service.create_invoice(db, payload, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_invoice_duplicate_items_raises(db):
    """Same customer + same item signature → duplicate detection."""
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="dup_inv@test.com")
    prod = await _make_product(db, admin, sku="DUP-INV-001")

    await _make_invoice(db, admin, cust.id, prod.id)

    with pytest.raises(AppException) as exc:
        await _make_invoice(db, admin, cust.id, prod.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_invoice_inter_state_uses_igst(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="igst@test.com")
    prod = await _make_product(db, admin, sku="IGST-001")

    payload = InvoiceCreate(
        customer_id=cust.id,
        is_inter_state=True,
        items=[InvoiceItemCreate(product_id=prod.id, quantity=1, unit_price=Decimal("1000"))],
    )
    inv = await invoice_service.create_invoice(db, payload, admin)
    assert inv.tax_amount > 0


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_invoice_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="get_inv@test.com")
    prod = await _make_product(db, admin, sku="GET-INV-001")
    created = await _make_invoice(db, admin, cust.id, prod.id)

    fetched = await invoice_service.get_invoice(db, created.id)
    assert fetched.id == created.id
    assert fetched.invoice_number == created.invoice_number


@pytest.mark.asyncio
async def test_get_invoice_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await invoice_service.get_invoice(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_invoices_returns_created(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="list_inv@test.com")
    prod = await _make_product(db, admin, sku="LIST-INV-001", name="ListInvProd")
    await _make_invoice(db, admin, cust.id, prod.id)

    result = await invoice_service.list_invoices(db, page=1, page_size=20)
    assert result.total >= 1


@pytest.mark.asyncio
async def test_list_invoices_customer_filter(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="flt_inv@test.com")
    prod = await _make_product(db, admin, sku="FLT-INV-001", name="FltInvProd")
    await _make_invoice(db, admin, cust.id, prod.id)

    result = await invoice_service.list_invoices(db, customer_id=cust.id)
    assert result.total >= 1
    assert all(item.invoice_number for item in result.items)


# -----------------------------------------------------------------------
# UPDATE (draft only)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_invoice_items_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="upd_inv@test.com")
    prod = await _make_product(db, admin, sku="UPD-INV-001", name="UpdInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=500)

    payload = InvoiceUpdate(
        version=inv.version,
        items=[InvoiceItemUpdate(product_id=prod.id, quantity=3, unit_price=Decimal("600"))],
    )
    updated = await invoice_service.update_invoice(db, inv.id, payload, admin)

    assert updated.gross_amount == Decimal("1800")
    assert updated.version == inv.version + 1


@pytest.mark.asyncio
async def test_update_non_draft_invoice_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="updnd_inv@test.com")
    prod = await _make_product(db, admin, sku="UPDND-INV-001", name="UpdNdInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    await invoice_service.verify_invoice(db, inv.id, admin)

    payload = InvoiceUpdate(
        version=inv.version + 1,
        items=[InvoiceItemUpdate(product_id=prod.id, quantity=1, unit_price=Decimal("500"))],
    )
    with pytest.raises(AppException) as exc:
        await invoice_service.update_invoice(db, inv.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_invoice_version_conflict_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="vc_inv@test.com")
    prod = await _make_product(db, admin, sku="VC-INV-001", name="VcInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    payload = InvoiceUpdate(
        version=999,
        items=[InvoiceItemUpdate(product_id=prod.id, quantity=1, unit_price=Decimal("500"))],
    )
    with pytest.raises(AppException) as exc:
        await invoice_service.update_invoice(db, inv.id, payload, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# VERIFY
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_invoice_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="vfy_inv@test.com")
    prod = await _make_product(db, admin, sku="VFY-INV-001", name="VfyInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    verified = await invoice_service.verify_invoice(db, inv.id, admin)
    assert verified.status == InvoiceStatus.verified


@pytest.mark.asyncio
async def test_verify_non_draft_invoice_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="vnd_inv@test.com")
    prod = await _make_product(db, admin, sku="VND-INV-001", name="VndInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    await invoice_service.verify_invoice(db, inv.id, admin)

    with pytest.raises(AppException) as exc:
        await invoice_service.verify_invoice(db, inv.id, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# APPLY DISCOUNT
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_discount_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="disc_inv@test.com")
    prod = await _make_product(db, admin, sku="DISC-INV-001", name="DiscInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=1000)

    payload = InvoiceDiscountApply(discount_amount=Decimal("100"))
    updated = await invoice_service.apply_discount(db, inv.id, payload, admin)

    assert updated.discount_amount == Decimal("100")
    assert updated.net_amount == (inv.gross_amount + inv.tax_amount) - Decimal("100")


@pytest.mark.asyncio
async def test_apply_discount_exceeds_total_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="disce_inv@test.com")
    prod = await _make_product(db, admin, sku="DISCE-INV-001", name="DisceInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=100)

    payload = InvoiceDiscountApply(discount_amount=Decimal("999999"))
    with pytest.raises(AppException) as exc:
        await invoice_service.apply_discount(db, inv.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# ADD PAYMENT
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_payment_partial_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="pay_inv@test.com")
    prod = await _make_product(db, admin, sku="PAY-INV-001", name="PayInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=1000)

    verified = await invoice_service.verify_invoice(db, inv.id, admin)

    payload = InvoicePaymentCreate(amount=Decimal("500"), payment_method="cash")
    payment = await invoice_service.add_payment(db, verified.id, payload, admin)

    assert payment.amount == Decimal("500")

    # Check status moved to partially_paid
    updated_inv = await invoice_service.get_invoice(db, inv.id)
    assert updated_inv.status == InvoiceStatus.partially_paid
    assert updated_inv.total_paid == Decimal("500")


@pytest.mark.asyncio
async def test_add_payment_full_marks_paid(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="fullpay_inv@test.com")
    prod = await _make_product(db, admin, sku="FPAY-INV-001", name="FpayInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=1000)

    verified = await invoice_service.verify_invoice(db, inv.id, admin)
    full_amount = verified.net_amount

    payload = InvoicePaymentCreate(amount=full_amount, payment_method="upi")
    await invoice_service.add_payment(db, verified.id, payload, admin)

    paid_inv = await invoice_service.get_invoice(db, inv.id)
    assert paid_inv.status == InvoiceStatus.paid
    assert paid_inv.balance_due == Decimal("0")


@pytest.mark.asyncio
async def test_add_payment_overpayment_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="ovpay_inv@test.com")
    prod = await _make_product(db, admin, sku="OVPAY-INV-001", name="OvpayInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=500)
    verified = await invoice_service.verify_invoice(db, inv.id, admin)

    payload = InvoicePaymentCreate(amount=verified.net_amount + Decimal("1"))
    with pytest.raises(AppException) as exc:
        await invoice_service.add_payment(db, verified.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_payment_on_draft_invoice_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="draftpay_inv@test.com")
    prod = await _make_product(db, admin, sku="DRAFTPAY-001", name="DraftPayProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    payload = InvoicePaymentCreate(amount=Decimal("100"))
    with pytest.raises(AppException) as exc:
        await invoice_service.add_payment(db, inv.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# CANCEL
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_draft_invoice_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="cancel_inv@test.com")
    prod = await _make_product(db, admin, sku="CANCEL-INV-001", name="CancelInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    result = await invoice_service.cancel_invoice(db, inv.id, admin)
    assert result.status == InvoiceStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_already_cancelled_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="dblcancel_inv@test.com")
    prod = await _make_product(db, admin, sku="DBLCANCEL-INV-001", name="DblCancelInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)

    await invoice_service.cancel_invoice(db, inv.id, admin)

    with pytest.raises(AppException) as exc:
        await invoice_service.cancel_invoice(db, inv.id, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_paid_invoice_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="cpaid_inv@test.com")
    prod = await _make_product(db, admin, sku="CPAID-INV-001", name="CpaidInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=100)
    verified = await invoice_service.verify_invoice(db, inv.id, admin)
    await invoice_service.add_payment(
        db, verified.id,
        InvoicePaymentCreate(amount=verified.net_amount),
        admin
    )

    with pytest.raises(AppException) as exc:
        await invoice_service.cancel_invoice(db, inv.id, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# FULFILL (mocked inventory movement)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fulfill_invoice_success(db):
    """
    Mocks apply_inventory_movement so the test doesn't need real
    InventoryBalance rows or a warehouse location.
    """
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="fulfill_inv@test.com")
    prod = await _make_product(db, admin, sku="FULFILL-INV-001", name="FulfillInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=5000)
    verified = await invoice_service.verify_invoice(db, inv.id, admin)
    await invoice_service.add_payment(
        db, verified.id,
        InvoicePaymentCreate(amount=verified.net_amount),
        admin,
    )
    paid = await invoice_service.get_invoice(db, inv.id)
    assert paid.status == InvoiceStatus.paid

    with patch(
        "app.services.billing.invoice_service.apply_inventory_movement",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await invoice_service.fulfill_invoice(db, inv.id, admin, paid.version)

    assert result.status == InvoiceStatus.fulfilled


@pytest.mark.asyncio
async def test_fulfill_unpaid_invoice_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="unfulfill_inv@test.com")
    prod = await _make_product(db, admin, sku="UNFULFILL-001", name="UnfulfillProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id)
    verified = await invoice_service.verify_invoice(db, inv.id, admin)

    with pytest.raises(AppException) as exc:
        await invoice_service.fulfill_invoice(db, inv.id, admin, verified.version)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fulfill_wrong_version_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="fver_inv@test.com")
    prod = await _make_product(db, admin, sku="FVER-INV-001", name="FverInvProd")
    inv = await _make_invoice(db, admin, cust.id, prod.id, unit_price=100)
    verified = await invoice_service.verify_invoice(db, inv.id, admin)
    await invoice_service.add_payment(
        db, verified.id,
        InvoicePaymentCreate(amount=verified.net_amount),
        admin,
    )

    with pytest.raises(AppException) as exc:
        await invoice_service.fulfill_invoice(db, inv.id, admin, version=999)
    assert exc.value.status_code == 409
