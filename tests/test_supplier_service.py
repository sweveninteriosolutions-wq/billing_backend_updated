# tests/test_supplier_service.py
#
# Covers: create_supplier, get_supplier, list_suppliers, update_supplier,
#         deactivate_supplier
# Validates: duplicate name guard, __dict__ lazy-safe mapper, version conflict.

import pytest
from decimal import Decimal

from tests.conftest import seed_user, StubUser
from app.services.masters import supplier_service
from app.schemas.masters.supplier_schemas import SupplierCreate, SupplierUpdate
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_supplier(db, admin, name="Test Supplier", phone="9876543210"):
    payload = SupplierCreate(
        name=name,
        contact_person="John Doe",
        phone=phone,
        email="supplier@test.com",
        address="123 Main St",
    )
    return await supplier_service.create_supplier(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_supplier_success(db):
    admin = await _setup(db)
    result = await _make_supplier(db, admin)

    assert result.id is not None
    assert result.name == "Test Supplier"
    assert result.supplier_code.startswith("SUP-")
    assert result.is_deleted is False
    assert result.version == 1


@pytest.mark.asyncio
async def test_create_supplier_duplicate_name_raises(db):
    admin = await _setup(db)
    await _make_supplier(db, admin, name="Unique Name")

    with pytest.raises(AppException) as exc:
        await _make_supplier(db, admin, name="Unique Name")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_supplier_no_lazy_load_crash(db):
    """
    Confirms _map_supplier uses __dict__.get() safely — no lazy='raise' trigger
    even though AuditMixin uses lazy='raise' on created_by/updated_by.
    """
    admin = await _setup(db)
    # Should complete without MissingGreenlet / greenlet_spawn error
    result = await _make_supplier(db, admin, name="LazyTestSupplier")
    assert result.created_by == admin.id


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_supplier_success(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="GetSupplier")

    fetched = await supplier_service.get_supplier(db, created.id)
    assert fetched.id == created.id
    assert fetched.name == "GetSupplier"


@pytest.mark.asyncio
async def test_get_supplier_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await supplier_service.get_supplier(db, 99999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_deactivated_supplier_raises(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="DeadSupplier")

    await supplier_service.deactivate_supplier(
        db=db, supplier_id=created.id, version=created.version, user=admin
    )

    with pytest.raises(AppException) as exc:
        await supplier_service.get_supplier(db, created.id)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# REGRESSION: SQLite compatibility — ILIKE must not be used in raw SQL
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_suppliers_sqlite_compatible_search(db):
    """
    REGRESSION FIX-2: Raw SQL must NOT use ILIKE (Postgres-only).
    Must use LOWER(col) LIKE LOWER(:val) for SQLite compatibility.
    This test fails with OperationalError if ILIKE is still present.
    """
    admin = await _setup(db)
    await _make_supplier(db, admin, name="SQLiteCompatSupplier")

    # This must not raise sqlite3.OperationalError: near "ILIKE": syntax error
    result = await supplier_service.list_suppliers(
        db=db, search="SQLiteCompat", is_deleted=False,
        page=1, page_size=10, sort_by="name", sort_order="asc",
    )
    assert result["total"] >= 1
    assert any("SQLiteCompat" in r["name"] for r in result["items"])


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_suppliers_returns_active(db):
    admin = await _setup(db)
    await _make_supplier(db, admin, name="ListSupplier1")

    result = await supplier_service.list_suppliers(
        db=db, search="ListSupplier", is_deleted=False,
        page=1, page_size=20, sort_by="name", sort_order="asc",
    )
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_list_suppliers_search_filter(db):
    admin = await _setup(db)
    await _make_supplier(db, admin, name="SearchableSupplier")

    result = await supplier_service.list_suppliers(
        db=db, search="Searchable", is_deleted=None,
        page=1, page_size=10, sort_by="name", sort_order="asc",
    )
    assert result["total"] >= 1
    assert all("Searchable" in r["name"] for r in result["items"])


@pytest.mark.asyncio
async def test_list_suppliers_invalid_sort_raises(db):
    admin = await _setup(db)
    with pytest.raises(AppException) as exc:
        await supplier_service.list_suppliers(
            db=db, search=None, is_deleted=None,
            page=1, page_size=10, sort_by="bad_field", sort_order="asc",
        )
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_supplier_contact_success(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="UpdateableSupplier")

    payload = SupplierUpdate(contact_person="Jane Doe", version=created.version)
    updated = await supplier_service.update_supplier(db, created.id, payload, admin)

    assert updated.contact_person == "Jane Doe"
    assert updated.version == created.version + 1


@pytest.mark.asyncio
async def test_update_supplier_version_conflict_raises(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="VersionSupplier")

    payload = SupplierUpdate(contact_person="X", version=999)
    with pytest.raises(AppException) as exc:
        await supplier_service.update_supplier(db, created.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_supplier_no_changes_raises(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="NoChangeSupplier")

    # Submit update with same values — service should detect no changes
    payload = SupplierUpdate(version=created.version)
    with pytest.raises(AppException) as exc:
        await supplier_service.update_supplier(db, created.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_supplier_duplicate_name_raises(db):
    admin = await _setup(db)
    await _make_supplier(db, admin, name="TakenName")
    s2 = await _make_supplier(db, admin, name="OtherSupplier")

    payload = SupplierUpdate(name="TakenName", version=s2.version)
    with pytest.raises(AppException) as exc:
        await supplier_service.update_supplier(db, s2.id, payload, admin)
    assert exc.value.status_code == 409


# -----------------------------------------------------------------------
# DEACTIVATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_supplier_success(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="DeactivateMe")

    result = await supplier_service.deactivate_supplier(
        db=db, supplier_id=created.id, version=created.version, user=admin
    )
    assert result.is_deleted is True


@pytest.mark.asyncio
async def test_deactivate_supplier_wrong_version_raises(db):
    admin = await _setup(db)
    created = await _make_supplier(db, admin, name="WrongVersionSupplier")

    with pytest.raises(AppException) as exc:
        await supplier_service.deactivate_supplier(
            db=db, supplier_id=created.id, version=999, user=admin
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_deactivate_nonexistent_supplier_raises(db):
    admin = await _setup(db)
    with pytest.raises(AppException) as exc:
        await supplier_service.deactivate_supplier(
            db=db, supplier_id=99999, version=1, user=admin
        )
    assert exc.value.status_code == 409
