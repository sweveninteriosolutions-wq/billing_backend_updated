# tests/test_purchase_order_service.py
#
# Covers: create_purchase_order, get_purchase_order, list_purchase_orders,
#         submit_purchase_order, approve_purchase_order, cancel_purchase_order
#
# BUG-3 REGRESSION: create_purchase_order previously used db.refresh() which
# failed to load items[i].product — this test suite validates the fix works.
#
# NOTE: apply_inventory_movement uses .with_for_update() which SQLite supports
# via aiosqlite in WAL mode. GRN verify is NOT tested here — see test_grn_service.py.

import pytest
from decimal import Decimal
from datetime import date, timedelta

from tests.conftest import seed_user, StubUser
from app.services.inventory import purchase_order_service
from app.services.masters import supplier_service, product_service
from app.services.inventory import inventory_location_service
from app.schemas.inventory.purchase_order_schemas import PurchaseOrderCreate, POItemCreate
from app.schemas.masters.supplier_schemas import SupplierCreate
from app.schemas.masters.product_schemas import ProductCreate
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_supplier(db, admin, name="POSupplier"):
    payload = SupplierCreate(name=name, phone="9000000000")
    return await supplier_service.create_supplier(db, payload, admin)


async def _make_product(db, admin, sku="PO-SKU-001", name="POProduct", price=500):
    payload = ProductCreate(
        sku=sku,
        name=name,
        hsn_code=9401,
        category="furniture",
        price=Decimal(str(price)),
        min_stock_threshold=0,
    )
    return await product_service.create_product(db, payload, admin)


async def _make_location(db, admin):
    """Create a minimal InventoryLocation directly in DB to avoid import complexity."""
    from app.models.inventory.inventory_location_models import InventoryLocation
    loc = InventoryLocation(
        code="LOC-TEST",
        name="Test Location",
        is_active=True,
        created_by_id=admin.id,
        updated_by_id=admin.id,
    )
    db.add(loc)
    await db.flush()
    return loc


async def _make_po(db, admin, supplier_id, location_id, product_id):
    payload = PurchaseOrderCreate(
        supplier_id=supplier_id,
        location_id=location_id,
        expected_date=date.today() + timedelta(days=7),
        notes="Test PO",
        items=[POItemCreate(product_id=product_id, quantity_ordered=10, unit_cost=Decimal("500"))],
    )
    return await purchase_order_service.create_purchase_order(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE  (BUG-3 regression)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_purchase_order_success(db):
    """
    BUG-3 REGRESSION: Previously crashed with MissingGreenlet because
    db.refresh() didn't load items[i].product. Now uses _fetch_po_with_relations
    which fully loads the nested graph. product_name must be non-None.
    """
    admin = await _setup(db)
    sup = await _make_supplier(db, admin)
    prod = await _make_product(db, admin)
    loc = await _make_location(db, admin)

    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    assert po.id is not None
    assert po.po_number.startswith("PO-")
    assert po.status == "draft"
    assert len(po.items) == 1
    # BUG-3: This was None before the fix — product sub-relation was not loaded
    assert po.items[0].product_name == "POProduct"
    assert po.items[0].quantity_ordered == 10
    assert po.supplier_name == "POSupplier"
    assert po.net_amount > 0


@pytest.mark.asyncio
async def test_create_po_invalid_supplier_raises(db):
    admin = await _setup(db)
    prod = await _make_product(db, admin, sku="PO-INV-SUP")
    loc = await _make_location(db, admin)

    payload = PurchaseOrderCreate(
        supplier_id=99999,
        location_id=loc.id,
        items=[POItemCreate(product_id=prod.id, quantity_ordered=1, unit_cost=Decimal("100"))],
    )
    with pytest.raises(AppException) as exc:
        await purchase_order_service.create_purchase_order(db, payload, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_po_invalid_location_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="LocTestSup")
    prod = await _make_product(db, admin, sku="PO-INV-LOC")

    payload = PurchaseOrderCreate(
        supplier_id=sup.id,
        location_id=99999,
        items=[POItemCreate(product_id=prod.id, quantity_ordered=1, unit_cost=Decimal("100"))],
    )
    with pytest.raises(AppException) as exc:
        await purchase_order_service.create_purchase_order(db, payload, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_po_empty_items_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="EmptyItemsSup")
    loc = await _make_location(db, admin)

    payload = PurchaseOrderCreate(
        supplier_id=sup.id,
        location_id=loc.id,
        items=[],
    )
    with pytest.raises(AppException) as exc:
        await purchase_order_service.create_purchase_order(db, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_purchase_order_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GetPOSup")
    prod = await _make_product(db, admin, sku="GET-PO-001")
    loc = await _make_location(db, admin)
    created = await _make_po(db, admin, sup.id, loc.id, prod.id)

    fetched = await purchase_order_service.get_purchase_order(db, created.id)
    assert fetched.id == created.id
    assert fetched.po_number == created.po_number
    assert fetched.items[0].product_name == "POProduct"


@pytest.mark.asyncio
async def test_get_purchase_order_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await purchase_order_service.get_purchase_order(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_purchase_orders_returns_created(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="ListPOSup")
    prod = await _make_product(db, admin, sku="LIST-PO-001", name="ListPOProd")
    loc = await _make_location(db, admin)
    await _make_po(db, admin, sup.id, loc.id, prod.id)

    result = await purchase_order_service.list_purchase_orders(db, page=1, page_size=20)
    assert result.total >= 1


@pytest.mark.asyncio
async def test_list_purchase_orders_status_filter(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="FilterPOSup")
    prod = await _make_product(db, admin, sku="FILTER-PO-001", name="FilterPOProd")
    loc = await _make_location(db, admin)
    await _make_po(db, admin, sup.id, loc.id, prod.id)

    result = await purchase_order_service.list_purchase_orders(db, status="draft")
    assert result.total >= 1
    assert all(item.status == "draft" for item in result.items)


# -----------------------------------------------------------------------
# SUBMIT
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_purchase_order_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="SubmitPOSup")
    prod = await _make_product(db, admin, sku="SUBMIT-PO-001", name="SubmitPOProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    submitted = await purchase_order_service.submit_purchase_order(db, po.id, po.version, admin)
    assert submitted.status == "submitted"
    assert submitted.version == po.version + 1


@pytest.mark.asyncio
async def test_submit_wrong_version_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="SumbitVSup")
    prod = await _make_product(db, admin, sku="SUBMIT-V-001", name="SubmitVProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    with pytest.raises(AppException) as exc:
        await purchase_order_service.submit_purchase_order(db, po.id, 999, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_already_submitted_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="SSub2Sup")
    prod = await _make_product(db, admin, sku="SSUB2-001", name="SSub2Prod")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)
    submitted = await purchase_order_service.submit_purchase_order(db, po.id, po.version, admin)

    with pytest.raises(AppException) as exc:
        await purchase_order_service.submit_purchase_order(db, po.id, submitted.version, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# APPROVE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_purchase_order_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="ApprovePOSup")
    prod = await _make_product(db, admin, sku="APP-PO-001", name="ApprovePOProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)
    submitted = await purchase_order_service.submit_purchase_order(db, po.id, po.version, admin)

    approved = await purchase_order_service.approve_purchase_order(
        db, po.id, submitted.version, admin
    )
    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_approve_from_draft_raises(db):
    """Cannot approve directly from draft — must submit first."""
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="AppDraftSup")
    prod = await _make_product(db, admin, sku="APPDRAFT-001", name="AppDraftProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    with pytest.raises(AppException) as exc:
        await purchase_order_service.approve_purchase_order(db, po.id, po.version, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# CANCEL
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_draft_po_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="CancelPOSup")
    prod = await _make_product(db, admin, sku="CANCEL-PO-001", name="CancelPOProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    cancelled = await purchase_order_service.cancel_purchase_order(db, po.id, po.version, admin)
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="DblCancelSup")
    prod = await _make_product(db, admin, sku="DBLCANCEL-001", name="DblCancelProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)
    cancelled = await purchase_order_service.cancel_purchase_order(db, po.id, po.version, admin)

    with pytest.raises(AppException) as exc:
        await purchase_order_service.cancel_purchase_order(db, po.id, cancelled.version, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_wrong_version_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="CancelVSup")
    prod = await _make_product(db, admin, sku="CANCELV-001", name="CancelVProd")
    loc = await _make_location(db, admin)
    po = await _make_po(db, admin, sup.id, loc.id, prod.id)

    with pytest.raises(AppException) as exc:
        await purchase_order_service.cancel_purchase_order(db, po.id, 999, admin)
    assert exc.value.status_code == 409
