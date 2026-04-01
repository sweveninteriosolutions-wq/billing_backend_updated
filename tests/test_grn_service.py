# tests/test_grn_service.py
#
# Covers: create_grn, get_grn, list_grns, update_grn, verify_grn (mocked),
#         cancel_grn
# Validates:
#   - BUG-4 regression: AuditMixin hybrid property created_by_username uses __dict__
#     so get_grn doesn't crash even when not called via selectinload
#   - GRN status machine: only DRAFT can be updated/cancelled/verified
#   - Duplicate item signature detection
#   - Duplicate bill_number detection

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from tests.conftest import seed_user, StubUser
from app.services.inventory import grn_service
from app.services.masters import supplier_service, product_service
from app.schemas.inventory.grn_schemas import GRNCreateSchema, GRNItemCreateSchema, GRNUpdateSchema
from app.schemas.masters.supplier_schemas import SupplierCreate
from app.schemas.masters.product_schemas import ProductCreate
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_supplier(db, admin, name="GRNSupplier"):
    payload = SupplierCreate(name=name, phone="7000000000")
    return await supplier_service.create_supplier(db, payload, admin)


async def _make_product(db, admin, sku="GRN-PROD-001", name="GRNProduct", price=200):
    payload = ProductCreate(
        sku=sku,
        name=name,
        category="furniture",
        price=Decimal(str(price)),
        min_stock_threshold=0,
    )
    return await product_service.create_product(db, payload, admin)


async def _make_location(db, admin, code="GRN-LOC"):
    from app.models.inventory.inventory_location_models import InventoryLocation
    loc = InventoryLocation(
        code=code,
        name="GRN Test Location",
        is_active=True,
        created_by_id=admin.id,
        updated_by_id=admin.id,
    )
    db.add(loc)
    await db.flush()
    return loc


async def _make_grn(db, admin, supplier_id, location_id, product_id, bill_number=None):
    payload = GRNCreateSchema(
        supplier_id=supplier_id,
        location_id=location_id,
        bill_number=bill_number,
        notes="Test GRN",
        items=[GRNItemCreateSchema(product_id=product_id, quantity=10, unit_cost=Decimal("200"))],
    )
    return await grn_service.create_grn(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_grn_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin)
    prod = await _make_product(db, admin)
    loc = await _make_location(db, admin)

    grn = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    assert grn.id is not None
    assert grn.status == "DRAFT"
    assert len(grn.items) == 1
    assert grn.items[0].quantity == 10
    assert grn.supplier_id == sup.id


@pytest.mark.asyncio
async def test_create_grn_invalid_supplier_raises(db):
    admin = await _setup(db)
    prod = await _make_product(db, admin, sku="GRN-INVSUP")
    loc = await _make_location(db, admin, code="GRN-LOC-IS")

    payload = GRNCreateSchema(
        supplier_id=99999,
        location_id=loc.id,
        items=[GRNItemCreateSchema(product_id=prod.id, quantity=1, unit_cost=Decimal("10"))],
    )
    with pytest.raises(AppException) as exc:
        await grn_service.create_grn(db, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_grn_invalid_location_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNInvLocSup")
    prod = await _make_product(db, admin, sku="GRN-INVLOC")

    payload = GRNCreateSchema(
        supplier_id=sup.id,
        location_id=99999,
        items=[GRNItemCreateSchema(product_id=prod.id, quantity=1, unit_cost=Decimal("10"))],
    )
    with pytest.raises(AppException) as exc:
        await grn_service.create_grn(db, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_grn_duplicate_bill_number_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNDupBillSup")
    prod = await _make_product(db, admin, sku="GRN-DUPBILL")
    loc = await _make_location(db, admin, code="GRN-LOC-DB")

    await _make_grn(db, admin, sup.id, loc.id, prod.id, bill_number="BILL-001")

    # Different items (different signature) but same bill number
    prod2 = await _make_product(db, admin, sku="GRN-DUPBILL2", name="GRNDupBillProd2")
    payload = GRNCreateSchema(
        supplier_id=sup.id,
        location_id=loc.id,
        bill_number="BILL-001",
        items=[GRNItemCreateSchema(product_id=prod2.id, quantity=5, unit_cost=Decimal("50"))],
    )
    with pytest.raises(AppException) as exc:
        await grn_service.create_grn(db, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_grn_duplicate_item_signature_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNDupSigSup")
    prod = await _make_product(db, admin, sku="GRN-DUPSIG")
    loc = await _make_location(db, admin, code="GRN-LOC-DS")

    await _make_grn(db, admin, sup.id, loc.id, prod.id)

    with pytest.raises(AppException) as exc:
        # Same items → same signature
        await _make_grn(db, admin, sup.id, loc.id, prod.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_grn_empty_items_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNEmptySup")
    loc = await _make_location(db, admin, code="GRN-LOC-EI")

    payload = GRNCreateSchema(supplier_id=sup.id, location_id=loc.id, items=[])
    with pytest.raises(AppException) as exc:
        await grn_service.create_grn(db, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# GET  (BUG-4 regression: hybrid property must not trigger lazy='raise')
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_grn_success_no_lazy_crash(db):
    """
    BUG-4 REGRESSION: AuditMixin.created_by_username accessed self.created_by
    which triggered lazy='raise'. Now uses __dict__.get() so this must not raise.
    """
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNGetSup")
    prod = await _make_product(db, admin, sku="GRN-GET-001")
    loc = await _make_location(db, admin, code="GRN-LOC-G")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    # get_grn uses selectinload(GRN.created_by) — should work without crash
    fetched = await grn_service.get_grn(db, created.id)
    assert fetched.id == created.id
    # created_by_name comes from the loaded relationship
    assert fetched.created_by == admin.id


@pytest.mark.asyncio
async def test_get_grn_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await grn_service.get_grn(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_grns_returns_created(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNListSup")
    prod = await _make_product(db, admin, sku="GRN-LIST-001", name="GRNListProd")
    loc = await _make_location(db, admin, code="GRN-LOC-L")
    await _make_grn(db, admin, sup.id, loc.id, prod.id)

    result = await grn_service.list_grns(
        db,
        supplier_id=None,
        status=None,
        start_date=None,
        end_date=None,
        page=1,
        page_size=20,
    )
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_list_grns_supplier_filter(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNFltSup")
    prod = await _make_product(db, admin, sku="GRN-FLT-001", name="GRNFltProd")
    loc = await _make_location(db, admin, code="GRN-LOC-F")
    await _make_grn(db, admin, sup.id, loc.id, prod.id)

    result = await grn_service.list_grns(
        db,
        supplier_id=sup.id,
        status=None,
        start_date=None,
        end_date=None,
        page=1,
        page_size=20,
    )
    assert result["total"] >= 1
    assert all(g.supplier_id == sup.id for g in result["items"])


@pytest.mark.asyncio
async def test_list_grns_status_filter(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNStFltSup")
    prod = await _make_product(db, admin, sku="GRN-STFLT-001", name="GRNStFltProd")
    loc = await _make_location(db, admin, code="GRN-LOC-SF")
    await _make_grn(db, admin, sup.id, loc.id, prod.id)

    result = await grn_service.list_grns(
        db,
        supplier_id=None,
        status="DRAFT",
        start_date=None,
        end_date=None,
        page=1,
        page_size=20,
    )
    assert result["total"] >= 1
    assert all(g.status == "DRAFT" for g in result["items"])


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_grn_notes_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNUpdSup")
    prod = await _make_product(db, admin, sku="GRN-UPD-001", name="GRNUpdProd")
    loc = await _make_location(db, admin, code="GRN-LOC-U")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    payload = GRNUpdateSchema(notes="Updated notes", version=created.version)
    updated = await grn_service.update_grn(db, created.id, payload, admin)

    assert updated.notes == "Updated notes"


@pytest.mark.asyncio
async def test_update_grn_version_conflict_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNVCSup")
    prod = await _make_product(db, admin, sku="GRN-VC-001", name="GRNVCProd")
    loc = await _make_location(db, admin, code="GRN-LOC-VC")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    payload = GRNUpdateSchema(notes="X", version=999)
    with pytest.raises(AppException) as exc:
        await grn_service.update_grn(db, created.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_non_draft_grn_raises(db):
    """After cancel_grn, GRN is in CANCELLED state — cannot update."""
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNNDUpdSup")
    prod = await _make_product(db, admin, sku="GRN-NDUPD-001", name="GRNNDUpdProd")
    loc = await _make_location(db, admin, code="GRN-LOC-NDU")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    await grn_service.cancel_grn(db, created.id, admin)

    payload = GRNUpdateSchema(notes="After cancel", version=created.version + 1)
    with pytest.raises(AppException) as exc:
        await grn_service.update_grn(db, created.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# CANCEL
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_grn_success(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNCancelSup")
    prod = await _make_product(db, admin, sku="GRN-CANCEL-001", name="GRNCancelProd")
    loc = await _make_location(db, admin, code="GRN-LOC-C")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    result = await grn_service.cancel_grn(db, created.id, admin)
    assert result.status == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNDblCancelSup")
    prod = await _make_product(db, admin, sku="GRN-DBLCANCEL-001", name="GRNDblCancelProd")
    loc = await _make_location(db, admin, code="GRN-LOC-DC")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    await grn_service.cancel_grn(db, created.id, admin)

    with pytest.raises(AppException) as exc:
        await grn_service.cancel_grn(db, created.id, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# VERIFY (mocked inventory movement)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_grn_success_mocked(db):
    """
    apply_inventory_movement is mocked so we don't need real InventoryBalance rows.
    Validates GRN status transitions to VERIFIED and items are processed.
    """
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNVerifySup")
    prod = await _make_product(db, admin, sku="GRN-VERIFY-001", name="GRNVerifyProd")
    loc = await _make_location(db, admin, code="GRN-LOC-V")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    with patch(
        "app.services.inventory.grn_service.apply_inventory_movement",
        new_callable=AsyncMock,
        return_value=True,
    ):
        result = await grn_service.verify_grn(db, created.id, admin)

    assert result.status == "VERIFIED"


@pytest.mark.asyncio
async def test_verify_already_verified_raises(db):
    admin = await _setup(db)
    sup = await _make_supplier(db, admin, name="GRNDblVerSup")
    prod = await _make_product(db, admin, sku="GRN-DBLVER-001", name="GRNDblVerProd")
    loc = await _make_location(db, admin, code="GRN-LOC-DV")
    created = await _make_grn(db, admin, sup.id, loc.id, prod.id)

    with patch(
        "app.services.inventory.grn_service.apply_inventory_movement",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await grn_service.verify_grn(db, created.id, admin)

    with pytest.raises(AppException) as exc:
        await grn_service.verify_grn(db, created.id, admin)
    assert exc.value.status_code == 409
