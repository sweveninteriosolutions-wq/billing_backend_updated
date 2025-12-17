# app/api/routes/activity_routes.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.users.user_schemas import APIResponse
from app.schemas.auth.activity_schemas import UserActivityFilters
from app.services.auth.activity_service import list_user_activities
from app.utils.check_roles import require_role
from app.utils.response import success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/activities", tags=["User Activities"])
logger = get_logger(__name__)


@router.get("/", response_model=APIResponse)
async def list_user_activities_api(
    filters: UserActivityFilters = Depends(),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_role(["admin"])),
):
    logger.info(
        "List user activities requested",
        extra=filters.dict(exclude_none=True),
    )

    result = await list_user_activities(db=db, filters=filters)

    return success_response(
        "User activities fetched successfully",
        result,
    )
