from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.users.user_schemas import (
    UserCreateSchema,
    UserUpdateSchema,
    UserResponseSchema,
    UsersListResponseSchema,
    UserDashboardResponseSchema,
)
from app.services.users.user_services import (
    create_user,
    list_users,
    update_user,
    get_user_dashboard_stats,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/users", tags=["Users"])


# =========================
# CREATE USER
# =========================
@router.post("/", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_user_api(
    payload: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    user = await create_user(db, payload, current_user)
    return {"msg": "User created successfully", "data": user}


# =========================
# LIST USERS
# =========================
@router.get("/", response_model=UsersListResponseSchema)
async def list_users_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    users = await list_users(db)
    return {"msg": "Users fetched", "data": users}


# =========================
# UPDATE USER (PATCH)
# =========================
@router.patch("/{user_id}", response_model=UserResponseSchema)
async def update_user_api(
    user_id: int,
    payload: UserUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    user = await update_user(db, user_id, payload, current_user)
    return {"msg": "User updated successfully", "data": user}


# =========================
# DEACTIVATE USER (SOFT DELETE)
# =========================
@router.delete("/{user_id}", response_model=UserResponseSchema)
async def deactivate_user_api(
    user_id: int,
    payload: UserUpdateSchema,  # must include version
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    payload.is_active = False

    user = await update_user(
        db=db,
        user_id=user_id,
        payload=payload,
        admin_user=current_user,
    )

    return {"msg": "User deactivated successfully", "data": user}


# =========================
# REACTIVATE USER
# =========================
@router.post("/{user_id}/activate", response_model=UserResponseSchema)
async def reactivate_user_api(
    user_id: int,
    payload: UserUpdateSchema,  # must include version
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    payload.is_active = True

    user = await update_user(
        db=db,
        user_id=user_id,
        payload=payload,
        admin_user=current_user,
    )

    return {"msg": "User reactivated successfully", "data": user}


# =========================
# DASHBOARD STATS
# =========================
@router.get("/dashboard/stats", response_model=UserDashboardResponseSchema)
async def user_dashboard_stats_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    stats = await get_user_dashboard_stats(db)
    return {"msg": "Dashboard stats fetched", "data": stats}
