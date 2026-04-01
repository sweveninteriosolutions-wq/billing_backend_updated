# tests/test_complaint_service.py
#
# Covers: create_complaint, get_complaint, list_complaints, update_complaint,
#         update_complaint_status, delete_complaint
# Validates: UNIQUE constraint enforcement (one complaint per customer+invoice+product),
#            status machine transitions (only allowed paths pass), soft-delete.

import pytest

from tests.conftest import seed_user, StubUser
from app.services.support import complaint_service
from app.services.masters import customer_service
from app.schemas.masters.customer_schema import CustomerCreate
from app.schemas.support.complaint_schemas import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintStatusUpdate,
)
from app.models.enums.complaint_status import ComplaintStatus, ComplaintPriority
from app.core.exceptions import AppException
from fastapi import HTTPException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _setup(db):
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _make_customer(db, admin, email="comp_cust@test.com"):
    payload = CustomerCreate(name="ComplaintCust", email=email, phone="9000000000")
    return await customer_service.create_customer(db, payload, admin)


async def _make_complaint(
    db,
    admin,
    customer_id,
    *,
    invoice_id=None,
    product_id=None,
    title="My Complaint",
    priority=ComplaintPriority.MEDIUM,
):
    payload = ComplaintCreate(
        customer_id=customer_id,
        invoice_id=invoice_id,
        product_id=product_id,
        title=title,
        priority=priority,
    )
    return await complaint_service.create_complaint(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_complaint_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin)

    result = await _make_complaint(db, admin, cust.id)
    assert result.data.id is not None
    assert result.data.customer_id == cust.id
    assert result.data.status == ComplaintStatus.OPEN
    assert result.data.priority == ComplaintPriority.MEDIUM


@pytest.mark.asyncio
async def test_create_complaint_with_priority(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="prio@test.com")

    result = await _make_complaint(
        db, admin, cust.id, title="Urgent Issue", priority=ComplaintPriority.HIGH
    )
    assert result.data.priority == ComplaintPriority.HIGH


@pytest.mark.asyncio
async def test_create_duplicate_complaint_raises(db):
    """
    Unique constraint: one open complaint per (customer_id, invoice_id, product_id).
    A second identical complaint must be rejected at DB level.
    """
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="dupcomp@test.com")

    await _make_complaint(db, admin, cust.id, invoice_id=None, product_id=None)

    # Same customer, same null invoice_id, same null product_id — should conflict
    with pytest.raises(HTTPException) as exc:
        await _make_complaint(db, admin, cust.id, invoice_id=None, product_id=None)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_complaint_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="get_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    fetched = await complaint_service.get_complaint(db, created.data.id)
    assert fetched.data.id == created.data.id
    assert fetched.data.title == "My Complaint"


@pytest.mark.asyncio
async def test_get_complaint_not_found(db):
    await _setup(db)
    with pytest.raises(HTTPException) as exc:
        await complaint_service.get_complaint(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_complaints_returns_created(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="list_comp@test.com")
    await _make_complaint(db, admin, cust.id)

    result = await complaint_service.list_complaints(
        db=db,
        customer_id=cust.id,
        invoice_id=None,
        product_id=None,
        status=None,
        priority=None,
        search=None,
        page=1,
        page_size=20,
    )
    assert result.total >= 1
    assert all(c.customer_id == cust.id for c in result.data)


@pytest.mark.asyncio
async def test_list_complaints_status_filter(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="status_comp@test.com")
    await _make_complaint(db, admin, cust.id)

    result = await complaint_service.list_complaints(
        db=db,
        customer_id=None,
        invoice_id=None,
        product_id=None,
        status=ComplaintStatus.OPEN,
        priority=None,
        search=None,
        page=1,
        page_size=20,
    )
    assert result.total >= 1
    assert all(c.status == ComplaintStatus.OPEN for c in result.data)


@pytest.mark.asyncio
async def test_list_complaints_search_filter(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="search_comp@test.com")
    await _make_complaint(db, admin, cust.id, title="Broken Drawer Handle")

    result = await complaint_service.list_complaints(
        db=db,
        customer_id=None,
        invoice_id=None,
        product_id=None,
        status=None,
        priority=None,
        search="Broken Drawer",
        page=1,
        page_size=20,
    )
    assert result.total >= 1


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_complaint_title_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="upd_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    payload = ComplaintUpdate(title="Updated Title")
    updated = await complaint_service.update_complaint(db, created.data.id, payload, admin)

    assert updated.data.title == "Updated Title"


@pytest.mark.asyncio
async def test_update_complaint_no_changes_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="noc_comp@test.com")
    created = await _make_complaint(db, admin, cust.id, title="Same Title")

    # Send same title — service detects no actual change
    payload = ComplaintUpdate(title="Same Title")
    with pytest.raises(HTTPException) as exc:
        await complaint_service.update_complaint(db, created.data.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_nonexistent_complaint_raises(db):
    admin = await _setup(db)
    payload = ComplaintUpdate(title="X")
    with pytest.raises(HTTPException) as exc:
        await complaint_service.update_complaint(db, 99999, payload, admin)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# STATUS TRANSITIONS
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_open_to_in_progress(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="st1_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    payload = ComplaintStatusUpdate(status=ComplaintStatus.IN_PROGRESS)
    updated = await complaint_service.update_complaint_status(db, created.data.id, payload, admin)
    assert updated.data.status == ComplaintStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_status_in_progress_to_resolved(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="st2_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    await complaint_service.update_complaint_status(
        db, created.data.id, ComplaintStatusUpdate(status=ComplaintStatus.IN_PROGRESS), admin
    )
    result = await complaint_service.update_complaint_status(
        db, created.data.id, ComplaintStatusUpdate(status=ComplaintStatus.RESOLVED), admin
    )
    assert result.data.status == ComplaintStatus.RESOLVED


@pytest.mark.asyncio
async def test_status_invalid_transition_raises(db):
    """OPEN → RESOLVED is not a valid transition per ALLOWED_STATUS_TRANSITIONS."""
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="st3_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    payload = ComplaintStatusUpdate(status=ComplaintStatus.RESOLVED)
    with pytest.raises(HTTPException) as exc:
        await complaint_service.update_complaint_status(db, created.data.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_status_open_to_closed_valid(db):
    """OPEN → CLOSED is allowed per ALLOWED_STATUS_TRANSITIONS."""
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="st4_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    result = await complaint_service.update_complaint_status(
        db, created.data.id, ComplaintStatusUpdate(status=ComplaintStatus.CLOSED), admin
    )
    assert result.data.status == ComplaintStatus.CLOSED


# -----------------------------------------------------------------------
# SOFT DELETE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_complaint_success(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="del_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    result = await complaint_service.delete_complaint(db, created.data.id, admin)
    assert result.message == "Complaint deleted successfully"


@pytest.mark.asyncio
async def test_delete_complaint_then_get_raises(db):
    admin = await _setup(db)
    cust = await _make_customer(db, admin, email="del2_comp@test.com")
    created = await _make_complaint(db, admin, cust.id)

    await complaint_service.delete_complaint(db, created.data.id, admin)

    with pytest.raises(HTTPException) as exc:
        await complaint_service.get_complaint(db, created.data.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_complaint_raises(db):
    admin = await _setup(db)
    with pytest.raises(HTTPException) as exc:
        await complaint_service.delete_complaint(db, 99999, admin)
    assert exc.value.status_code == 404
