# tests/test_customer_service.py
#
# Covers: create_customer, get_customer, list_customers, update_customer,
#         deactivate_customer
# Validates: no lazy-load errors, version conflict handling, duplicate email.

import pytest

from tests.conftest import seed_user, StubUser
from app.services.masters import customer_service
from app.schemas.masters.customer_schema import CustomerCreate, CustomerUpdate
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_customer(db, admin, email="cust@test.com", name="Test Customer"):
    payload = CustomerCreate(name=name, email=email, phone="9999999999")
    return await customer_service.create_customer(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_customer_success(db):
    admin = await _setup(db)
    result = await _make_customer(db, admin)

    assert result.id is not None
    assert result.email == "cust@test.com"
    assert result.name == "Test Customer"
    assert result.customer_code.startswith("CUST-")
    assert result.is_active is True


@pytest.mark.asyncio
async def test_create_customer_duplicate_email_raises(db):
    admin = await _setup(db)
    await _make_customer(db, admin, email="dup@test.com")

    with pytest.raises(AppException) as exc:
        await _make_customer(db, admin, email="dup@test.com")
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_customer_success(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    fetched = await customer_service.get_customer(db, created.id)
    assert fetched.id == created.id
    assert fetched.email == "cust@test.com"


@pytest.mark.asyncio
async def test_get_customer_not_found(db):
    await _setup(db)
    with pytest.raises(AppException) as exc:
        await customer_service.get_customer(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_customers_returns_created(db):
    admin = await _setup(db)
    await _make_customer(db, admin, email="list1@test.com", name="ListCust1")

    result = await customer_service.list_customers(
        db=db, name="ListCust1", email=None, phone=None,
        is_active=None, page=1, page_size=10,
    )
    assert result.total >= 1
    names = [r.name for r in result.items]
    assert "ListCust1" in names


@pytest.mark.asyncio
async def test_list_customers_email_filter(db):
    admin = await _setup(db)
    await _make_customer(db, admin, email="filtered@test.com", name="FilteredCust")

    result = await customer_service.list_customers(
        db=db, name=None, email="filtered", phone=None,
        is_active=None, page=1, page_size=10,
    )
    assert result.total >= 1
    emails = [r.email for r in result.items]
    assert all("filtered" in e for e in emails)


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_customer_name_success(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    payload = CustomerUpdate(name="New Name", version=created.version)
    updated = await customer_service.update_customer(db, created.id, payload, admin)

    assert updated.name == "New Name"
    assert updated.version == created.version + 1


@pytest.mark.asyncio
async def test_update_customer_version_conflict_raises(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    payload = CustomerUpdate(name="X", version=999)
    with pytest.raises(AppException) as exc:
        await customer_service.update_customer(db, created.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_customer_no_changes_raises(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    # Send an update with no actual fields
    payload = CustomerUpdate(version=created.version)
    with pytest.raises(AppException) as exc:
        await customer_service.update_customer(db, created.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# DEACTIVATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_customer_success(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    result = await customer_service.deactivate_customer(db, created.id, admin)
    assert result.is_active is False


@pytest.mark.asyncio
async def test_deactivate_already_inactive_raises(db):
    admin = await _setup(db)
    created = await _make_customer(db, admin)

    await customer_service.deactivate_customer(db, created.id, admin)

    with pytest.raises(AppException) as exc:
        await customer_service.deactivate_customer(db, created.id, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_nonexistent_customer_raises(db):
    admin = await _setup(db)
    with pytest.raises(AppException) as exc:
        await customer_service.deactivate_customer(db, 99999, admin)
    assert exc.value.status_code == 404
