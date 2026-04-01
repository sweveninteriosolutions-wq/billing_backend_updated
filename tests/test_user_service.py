# tests/test_user_service.py
#
# Covers: create_user, list_users, get_user_by_id, update_user,
#         deactivate_user, reactivate_user
# Validates: no lazy-load errors, complete mapped data, all edge cases.

import pytest
import pytest_asyncio

from tests.conftest import seed_user, StubUser
from app.services.users import user_services
from app.schemas.users.user_schemas import (
    UserCreateSchema,
    UserUpdateSchema,
    UserListFilters,
)
from app.core.exceptions import AppException


# -----------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------

async def _make_admin(db) -> StubUser:
    """Insert the real admin row required by FK constraints."""
    await seed_user(db, id=1, username="admin@test.com", role="admin")
    return StubUser(id=1, username="admin@test.com", role="admin")


async def _create_test_user(db, admin, email="user@test.com", role="cashier") -> None:
    payload = UserCreateSchema(
        email=email,
        password="Passw0rd123!",
        role=role,
    )
    return await user_services.create_user(db, payload, admin)


# -----------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_success(db):
    admin = await _make_admin(db)
    result = await _create_test_user(db, admin)

    assert result.username == "user@test.com"
    assert result.role == "cashier"
    assert result.is_active is True
    assert result.id is not None


@pytest.mark.asyncio
async def test_create_user_duplicate_email_raises(db):
    admin = await _make_admin(db)
    await _create_test_user(db, admin, email="dup@test.com")

    with pytest.raises(AppException) as exc:
        await _create_test_user(db, admin, email="dup@test.com")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_user_invalid_role_raises(db):
    admin = await _make_admin(db)
    payload = UserCreateSchema(
        email="badrole@test.com",
        password="Passw0rd123!",
        role="superuser",  # not in ALLOWED_ROLES
    )
    with pytest.raises(AppException) as exc:
        await user_services.create_user(db, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# GET
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_by_id_success(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    fetched = await user_services.get_user_by_id(db, created.id)
    assert fetched.id == created.id
    assert fetched.username == "user@test.com"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(db):
    await _make_admin(db)
    with pytest.raises(AppException) as exc:
        await user_services.get_user_by_id(db, 99999)
    assert exc.value.status_code == 404


# -----------------------------------------------------------------------
# LIST
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_returns_results(db):
    admin = await _make_admin(db)
    await _create_test_user(db, admin, email="list1@test.com", role="sales")
    await _create_test_user(db, admin, email="list2@test.com", role="cashier")

    filters = UserListFilters(role="sales")
    result = await user_services.list_users(db, filters)

    assert result["total"] >= 1
    assert any(u.username == "list1@test.com" for u in result["items"])


@pytest.mark.asyncio
async def test_list_users_search_filter(db):
    admin = await _make_admin(db)
    await _create_test_user(db, admin, email="searchme@test.com")

    filters = UserListFilters(search="searchme")
    result = await user_services.list_users(db, filters)

    assert result["total"] >= 1
    assert all("searchme" in u.username for u in result["items"])


@pytest.mark.asyncio
async def test_list_users_empty_when_no_match(db):
    await _make_admin(db)
    filters = UserListFilters(search="zzznobodymatchesthis")
    result = await user_services.list_users(db, filters)
    assert result["total"] == 0
    assert result["items"] == []


# -----------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_user_role_success(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin, role="cashier")

    payload = UserUpdateSchema(role="sales", version=created.version)
    updated = await user_services.update_user(db, created.id, payload, admin)

    assert updated.role == "sales"


@pytest.mark.asyncio
async def test_update_user_version_conflict_raises(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    payload = UserUpdateSchema(role="sales", version=999)  # wrong version
    with pytest.raises(AppException) as exc:
        await user_services.update_user(db, created.id, payload, admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_user_cannot_change_own_role(db):
    admin = await _make_admin(db)

    payload = UserUpdateSchema(role="cashier", version=admin.version)
    with pytest.raises(AppException) as exc:
        await user_services.update_user(db, admin.id, payload, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_user_duplicate_email_raises(db):
    admin = await _make_admin(db)
    u1 = await _create_test_user(db, admin, email="taken@test.com")
    u2 = await _create_test_user(db, admin, email="other@test.com")

    payload = UserUpdateSchema(email="taken@test.com", version=u2.version)
    with pytest.raises(AppException) as exc:
        await user_services.update_user(db, u2.id, payload, admin)
    assert exc.value.status_code == 400


# -----------------------------------------------------------------------
# DEACTIVATE / REACTIVATE
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deactivate_user_success(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    result = await user_services.deactivate_user(db, created.id, created.version, admin)
    assert result.is_active is False


@pytest.mark.asyncio
async def test_deactivate_own_account_raises(db):
    admin = await _make_admin(db)
    with pytest.raises(AppException) as exc:
        await user_services.deactivate_user(db, admin.id, admin.version, admin)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_deactivate_already_inactive_raises(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    await user_services.deactivate_user(db, created.id, created.version, admin)
    # version is now +1; try deactivating again with the old version
    with pytest.raises(AppException):
        await user_services.deactivate_user(db, created.id, created.version, admin)


@pytest.mark.asyncio
async def test_reactivate_user_success(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    deactivated = await user_services.deactivate_user(db, created.id, created.version, admin)
    reactivated = await user_services.reactivate_user(db, created.id, deactivated.version, admin)
    assert reactivated.is_active is True


@pytest.mark.asyncio
async def test_reactivate_already_active_raises(db):
    admin = await _make_admin(db)
    created = await _create_test_user(db, admin)

    with pytest.raises(AppException) as exc:
        await user_services.reactivate_user(db, created.id, created.version, admin)
    assert exc.value.status_code == 409
