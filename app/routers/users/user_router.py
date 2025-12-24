from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.users.user_schemas import (
    APIResponse,
    UserCreateSchema,
    UserUpdateSchema,
    UserListFilters,
    VersionOnlySchema,
    UserListResponseSchema

)
from app.services.users.user_services import (
    create_user,
    list_users,
    get_user_by_id,
    update_user,
    get_user_dashboard_stats,
    deactivate_user,
    reactivate_user,
)
from app.utils.check_roles import require_role
from app.utils.response import success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


@router.post("/", response_model=APIResponse)
async def create_user_api(
    payload: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("Create user request", extra={"email": payload.email})
    user = await create_user(db, payload, admin)
    return success_response("User created successfully", user)


@router.get(
    "/",
    response_model=APIResponse[UserListResponseSchema]
)
async def list_users_api(
    filters: UserListFilters = Depends(),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("List users request", extra=filters.dict())
    users = await list_users(db, filters)
    return success_response("Users fetched", users)



@router.get("/{user_id}", response_model=APIResponse)
async def get_user_api(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("Get user by id", extra={"user_id": user_id})
    user = await get_user_by_id(db, user_id)
    return success_response("User fetched", user)


@router.patch("/{user_id}", response_model=APIResponse)
async def update_user_api(
    user_id: int,
    payload: UserUpdateSchema,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("Update user", extra={"user_id": user_id})
    user = await update_user(db, user_id, payload, admin)
    return success_response("User updated successfully", user)


@router.delete("/{user_id}", response_model=APIResponse)
async def deactivate_user_api(
    user_id: int,
    payload: VersionOnlySchema,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("Deactivate user", extra={"user_id": user_id})
    user = await deactivate_user(db, user_id, payload.version, admin)
    return success_response("User deactivated successfully", user)


@router.post("/{user_id}/activate", response_model=APIResponse)
async def reactivate_user_api(
    user_id: int,
    payload: VersionOnlySchema,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("Reactivate user", extra={"user_id": user_id})
    user = await reactivate_user(db, user_id, payload.version, admin)
    return success_response("User reactivated successfully", user)


@router.get("/dashboard/stats", response_model=APIResponse)
async def dashboard_stats_api(
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info("User dashboard stats requested")
    stats = await get_user_dashboard_stats(db)
    return success_response("Dashboard stats fetched", stats)
