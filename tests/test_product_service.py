# tests/test_product_service.py
#
# Covers: create_product, get_product, list_products, update_product,
#         deactivate_product, reactivate_product
# Validates: lazy="raise" safety (created_by/updated_by via selectinload),
#            SKU uniqueness, version conflicts.

import pytest
from decimal import Decimal

from tests.conftest import seed_user, StubUser
from app.services.masters import product_service
from app.schemas.masters.product_schemas import ProductCreate, ProductUpdate
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_product(db, admin, sku="SKU-001", name="Chair", price=500):
    payload = ProductCreate(
        sku=sku,
        name=name,
        hsn_code=9401,
        category="furniture",
        price=Decimal(str(price)),
        min_stock_threshold=5,
    )
    return await product_service.create_product(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_product_success(db):
    admin = await _setup(db)
    result = await _make_product(db, admin)

    assert result.id is not None
    assert result.sku == "SKU-001"
    assert result.name == "Chair"
    assert result.price == Decimal("500")
    assert result.is_active is True
    assert result.version == 1


@pytest.mark.asyncio
async def test_create_product_duplicate_sku_raises(db):
    admin = await _setup(db)
    await _make_product(db, admin, sku="DUP-SKU", name="Original")

    with pytest.raises(AppException) as exc:
        await _make_product(db, admin, sku="DUP-SKU", name="Duplicate")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_product_no_lazy_load_crash(db):
    """
    Verifies that _map_product uses __dict__ to access created_by/updated_by
    and does NOT trigger lazy='raise' even though AuditMixin uses lazy='raise'.
    """
    admin = await _setup(db)
    # This should NOT raise MissingGreenlet / lazy="raise"
    result = await _make_product(db, admin, sku="LAZY-SKU", name="LazyTest")
    # created_by_name comes from selectinload, should be present
    assert result.created_by == admin.id


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_product_success(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="GET-001", name="Sofa")

    fetched = await product_service.get_product(db, created.id)
    assert fetched.sku == "GET-001"
    assert fetched.name == "Sofa"


@pytest.mark.asyncio
async def test_get_product_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await product_service.get_product(db, 99999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_deactivated_product_raises(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="DEL-001", name="Deleted Product")

    await product_service.deactivate_product(db, created.id, created.version, admin)

    with pytest.raises(AppException) as exc:
        await product_service.get_product(db, created.id)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_products_returns_active(db):
    admin = await _setup(db)
    await _make_product(db, admin, sku="LIST-001", name="ListProduct1")

    result = await product_service.list_products(
        db=db, search="ListProduct", category=None,
        supplier_id=None, min_price=None, max_price=None,
        page=1, page_size=20, sort_by="name", order="asc",
    )
    assert result.total >= 1


@pytest.mark.asyncio
async def test_list_products_category_filter(db):
    admin = await _setup(db)
    await _make_product(db, admin, sku="CAT-001", name="CatProduct")

    result = await product_service.list_products(
        db=db, search=None, category="furniture",
        supplier_id=None, min_price=None, max_price=None,
        page=1, page_size=20, sort_by="name", order="asc",
    )
    assert result.total >= 1
    for p in result.items:
        assert p.category == "furniture"


@pytest.mark.asyncio
async def test_list_products_invalid_sort_raises(db):
    admin = await _setup(db)
    with pytest.raises(AppException) as exc:
        await product_service.list_products(
            db=db, search=None, category=None,
            supplier_id=None, min_price=None, max_price=None,
            page=1, page_size=10, sort_by="not_a_field", order="asc",
        )
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_product_price_success(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="UPD-001", name="UpdateProd")

    payload = ProductUpdate(price=Decimal("999.99"), version=created.version)
    updated = await product_service.update_product(db, created.id, payload, admin)

    assert updated.price == Decimal("999.99")
    assert updated.version == created.version + 1


@pytest.mark.asyncio
async def test_update_product_version_conflict_raises(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="VER-001", name="VerProd")

    payload = ProductUpdate(price=Decimal("1.00"), version=999)
    with pytest.raises(AppException) as exc:
        await product_service.update_product(db, created.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_product_no_changes_raises(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="NOC-001", name="NoChange")

    # Pass the same price — service should detect no actual changes
    payload = ProductUpdate(price=Decimal("500"), version=created.version)
    with pytest.raises(AppException) as exc:
        await product_service.update_product(db, created.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# DEACTIVATE / REACTIVATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_product_success(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="DEACT-001", name="DeactProd")

    result = await product_service.deactivate_product(db, created.id, created.version, admin)
    assert result.is_active is False


@pytest.mark.asyncio
async def test_deactivate_wrong_version_raises(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="DVR-001", name="DVRProd")

    with pytest.raises(AppException) as exc:
        await product_service.deactivate_product(db, created.id, 999, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reactivate_product_success(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="REACT-001", name="ReactProd")

    deactivated = await product_service.deactivate_product(db, created.id, created.version, admin)
    reactivated = await product_service.reactivate_product(db, created.id, admin)
    assert reactivated.is_active is True


@pytest.mark.asyncio
async def test_reactivate_active_product_raises(db):
    admin = await _setup(db)
    created = await _make_product(db, admin, sku="RA2-001", name="StillActive")

    # Already active — reactivate should fail
    with pytest.raises(AppException) as exc:
        await product_service.reactivate_product(db, created.id, admin)
    assert exc.value.status_code == 409
