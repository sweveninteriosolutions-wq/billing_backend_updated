# tests/test_quotation_service.py
#
# Covers: create_quotation, get_quotation, list_quotations, update_quotation,
#         send_quotation, approve_quotation, cancel_quotation, delete_quotation
# Validates: .returning() removal works on SQLite, version conflicts, state
#            machine transitions, and lazy-load safety on items.

import pytest
from datetime import date, timedelta
from decimal import Decimal

from tests.conftest import seed_user, StubUser
from app.services.billing import quotation_service
from app.services.masters import customer_service, product_service
from app.schemas.billing.quotation_schemas import (
    QuotationCreate,
    QuotationItemCreate,
    QuotationUpdate,
    QuotationItemUpdate,
)
from app.schemas.masters.customer_schema import CustomerCreate
from app.schemas.masters.product_schemas import ProductCreate
from app.core.exceptions import AppException
from app.models.enums.quotation_status import QuotationStatus


# -----------------------------------------------------------------------
# FIXTURES / HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_customer(db, admin):
    payload = CustomerCreate(name="QCust", email="qcust@test.com", phone="9876543210")
    return await customer_service.create_customer(db, payload, admin)


async def _make_product(db, admin, sku="SKU-Q1", price=1000):
    payload = ProductCreate(
        sku=sku,
        name=f"Product {sku}",
        hsn_code=1234,
        category="furniture",
        price=Decimal(str(price)),
        min_stock_threshold=5,
    )
    return await product_service.create_product(db, payload, admin)


async def _make_quotation(db, admin, customer_id, product_id):
    payload = QuotationCreate(
        customer_id=customer_id,
        is_inter_state=False,
        valid_until=date.today() + timedelta(days=30),
        items=[QuotationItemCreate(product_id=product_id, quantity=2)],
    )
    return await quotation_service.create_quotation(db, payload, admin)


# -----------------------------------------------------------------------
# REGRESSION: HSN code must be derived from DB product, never from payload
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quotation_item_hsn_code_copied_from_product(db):
    """
    REGRESSION FIX-1: QuotationItem.hsn_code must be copied from the DB product
    record, never left as None. Verifies the root cause is fixed end-to-end.
    """
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-HSN")  # hsn_code=1234

    q = await _make_quotation(db, admin, cust.id, prod.id)

    assert q.id is not None
    assert len(q.items) == 1
    # The service must have copied hsn_code from Product, not from the payload
    assert q.items[0].hsn_code == 1234, (
        "hsn_code must be derived from the Product DB record. "
        "If None, the service is not fetching the product before inserting the item."
    )


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_quotation_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin)

    q = await _make_quotation(db, admin, cust.id, prod.id)

    assert q.id is not None
    assert q.status == QuotationStatus.draft
    assert q.quotation_number.startswith("QT-")
    assert len(q.items) == 1
    assert q.subtotal_amount > 0
    assert q.tax_amount > 0
    assert q.total_amount == q.subtotal_amount + q.tax_amount


@pytest.mark.asyncio
async def test_create_quotation_invalid_customer_raises(db):
    admin = await _setup(db)
    prod = await _make_product(db, admin, sku="SKU-Q99")

    payload = QuotationCreate(
        customer_id=99999,
        is_inter_state=False,
        valid_until=date.today() + timedelta(days=10),
        items=[QuotationItemCreate(product_id=prod.id, quantity=1)],
    )
    with pytest.raises(AppException) as exc:
        await quotation_service.create_quotation(db, payload, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_quotation_invalid_product_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)

    payload = QuotationCreate(
        customer_id=cust.id,
        is_inter_state=False,
        valid_until=date.today() + timedelta(days=10),
        items=[QuotationItemCreate(product_id=99999, quantity=1)],
    )
    with pytest.raises(AppException) as exc:
        await quotation_service.create_quotation(db, payload, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_quotation_duplicate_draft_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-DUP")

    await _make_quotation(db, admin, cust.id, prod.id)

    with pytest.raises(AppException) as exc:
        await _make_quotation(db, admin, cust.id, prod.id)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_quotations_returns_created(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-L1")
    await _make_quotation(db, admin, cust.id, prod.id)

    result = await quotation_service.list_quotations(db, page=1, page_size=20)
    assert result.total >= 1


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_quotation_notes_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-U1")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    payload = QuotationUpdate(notes="Updated note", version=q.version)
    updated = await quotation_service.update_quotation(db, q.id, payload, admin)

    assert updated.notes == "Updated note"
    assert updated.version == q.version + 1


@pytest.mark.asyncio
async def test_update_quotation_version_conflict_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-VC")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    payload = QuotationUpdate(notes="X", version=999)
    with pytest.raises(AppException) as exc:
        await quotation_service.update_quotation(db, q.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_non_draft_quotation_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-ND")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    # Move to sent
    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)

    payload = QuotationUpdate(notes="Can't edit", version=sent.version)
    with pytest.raises(AppException) as exc:
        await quotation_service.update_quotation(db, q.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# SEND  (tests .returning() removal)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_quotation_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-S1")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)
    assert sent.status == QuotationStatus.sent


@pytest.mark.asyncio
async def test_send_quotation_wrong_version_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-SV")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    with pytest.raises(AppException) as exc:
        await quotation_service.send_quotation(db, q.id, 999, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_send_already_sent_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-SS")
    q = await _make_quotation(db, admin, cust.id, prod.id)
    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)

    # Try to send again — should fail (not in draft)
    with pytest.raises(AppException) as exc:
        await quotation_service.send_quotation(db, q.id, sent.version, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# APPROVE  (tests .returning() removal, ERP-028 both draft and sent)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_from_sent_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-A1")
    q = await _make_quotation(db, admin, cust.id, prod.id)
    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)

    approved = await quotation_service.approve_quotation(db, q.id, sent.version, admin)
    assert approved.status == QuotationStatus.approved


@pytest.mark.asyncio
async def test_approve_from_draft_success(db):
    """ERP-028: approval directly from draft is also allowed."""
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-AD")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    approved = await quotation_service.approve_quotation(db, q.id, q.version, admin)
    assert approved.status == QuotationStatus.approved


@pytest.mark.asyncio
async def test_approve_wrong_version_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-AV")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    with pytest.raises(AppException) as exc:
        await quotation_service.approve_quotation(db, q.id, 999, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# CANCEL  (tests .returning() removal)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_draft_quotation(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-C1")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    cancelled = await quotation_service.cancel_quotation(db, q.id, q.version, admin)
    assert cancelled.status == QuotationStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_sent_quotation(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-CS")
    q = await _make_quotation(db, admin, cust.id, prod.id)
    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)

    cancelled = await quotation_service.cancel_quotation(db, q.id, sent.version, admin)
    assert cancelled.status == QuotationStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_wrong_version_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-CV")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    with pytest.raises(AppException) as exc:
        await quotation_service.cancel_quotation(db, q.id, 999, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# DELETE (soft)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_draft_quotation_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-D1")
    q = await _make_quotation(db, admin, cust.id, prod.id)

    deleted = await quotation_service.delete_quotation(db, q.id, q.version, admin)
    assert deleted.id == q.id


@pytest.mark.asyncio
async def test_delete_non_draft_quotation_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)
    prod = await _make_product(db, admin, sku="SKU-DNd")
    q = await _make_quotation(db, admin, cust.id, prod.id)
    sent = await quotation_service.send_quotation(db, q.id, q.version, admin)

    with pytest.raises(AppException) as exc:
        await quotation_service.delete_quotation(db, q.id, sent.version, admin)
    assert exc.value.status_code == 409
