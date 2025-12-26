from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from datetime import date

from app.models.users.user_models import User
from app.schemas.users.user_schemas import (
    UserCreateSchema,
    UserUpdateSchema,
    UserListFilters,
    UserListItemSchema,
    UserDetailSchema,
    UserDashboardStatsSchema,
)
from app.core.security import hash_password
from app.utils.activity_helpers import emit_activity
from app.constants.activity_codes import ActivityCode
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_ROLES = {"admin", "cashier", "sales", "inventory"}


# =========================
# CREATE USER
# =========================
async def create_user(db: AsyncSession, payload: UserCreateSchema, admin: User):
    if payload.role not in ALLOWED_ROLES:
        raise AppException(400, "Invalid role", ErrorCode.USER_ROLE_INVALID)

    exists = await db.scalar(select(User.id).where(User.username == payload.email))
    if exists:
        raise AppException(400, "User already exists", ErrorCode.USER_EMAIL_EXISTS)

    user = User(
        username=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        created_by_admin_id=admin.id,
    )

    db.add(user)
    await db.flush()

    await emit_activity(
        db=db,
        user_id=admin.id,
        username=admin.username,
        code=ActivityCode.CREATE_USER,
        actor_role=admin.role.capitalize(),
        actor_email=admin.username,
        target_email=user.username,
        target_role=user.role.capitalize(),
    )

    await db.commit()
    await db.refresh(user)

    logger.info("User created", extra={"user_id": user.id})
    return UserDetailSchema.from_orm(user)


# =========================
# LIST USERS
# =========================
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

async def list_users(
    db: AsyncSession,
    filters: UserListFilters,
) -> dict:
    base_stmt = select(User)

    # --------------------
    # Filters
    # --------------------
    if filters.search:
        base_stmt = base_stmt.where(
            User.username.ilike(f"%{filters.search}%")
        )

    if filters.role:
        base_stmt = base_stmt.where(User.role == filters.role)

    if filters.is_active is not None:
        base_stmt = base_stmt.where(User.is_active == filters.is_active)

    if filters.is_online is not None:
        base_stmt = base_stmt.where(User.is_online == filters.is_online)

    if filters.created_today:
        base_stmt = base_stmt.where(
            func.date(User.created_at) == date.today()
        )

    if filters.created_by:
        base_stmt = base_stmt.where(
            User.created_by_admin_id == filters.created_by
        )

    # --------------------
    # Total count (before pagination)
    # --------------------
    total = await db.scalar(
        select(func.count()).select_from(base_stmt.subquery())
    )

    # --------------------
    # Sorting (safe)
    # --------------------
    sort_map = {
        "created_at": User.created_at,
        "username": User.username,
    }

    sort_col = sort_map.get(filters.sort_by)
    if not sort_col:
        raise AppException(400, "Invalid sort field", ErrorCode.VALIDATION_ERROR)

    sort_col = (
        sort_col.desc()
        if filters.sort_order.lower() == "desc"
        else sort_col.asc()
    )

    # --------------------
    # Pagination
    # --------------------
    page = max(filters.page, 1)
    page_size = filters.page_size
    offset = (page - 1) * page_size

    stmt = (
        base_stmt
        .order_by(sort_col)
        .limit(page_size)
        .offset(offset)
    )

    result = await db.execute(stmt)
    users = result.scalars().all()

    # --------------------
    # Response (MATCHES SCHEMA)
    # --------------------
    return {
        "items": [
            UserListItemSchema(
                id=u.id,
                username=u.username,
                role=u.role,
                is_active=u.is_active,
                is_online=u.is_online,
                last_login=u.last_login,
                version=u.version,
            )
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# =========================
# GET USER BY ID
# =========================
async def get_user_by_id(db: AsyncSession, user_id: int):
    user = await db.get(User, user_id)
    if not user:
        raise AppException(404, "User not found", ErrorCode.USER_NOT_FOUND)
    return UserDetailSchema.from_orm(user)


# =========================
# UPDATE USER
# =========================
async def update_user(
    db: AsyncSession,
    user_id: int,
    payload: UserUpdateSchema,
    admin: User,
):
    # -------------------------------------------------
    # FETCH USER
    # -------------------------------------------------
    user = await db.get(User, user_id)
    if not user:
        raise AppException(404, "User not found", ErrorCode.USER_NOT_FOUND)

    # -------------------------------------------------
    # CAPTURE PREVIOUS STATE (FOR AUDIT)
    # -------------------------------------------------
    prev_email = user.username
    prev_role = user.role
    prev_is_active = user.is_active

    values: dict = {}

    # -------------------------------------------------
    # EMAIL UPDATE
    # -------------------------------------------------
    if payload.email and payload.email != user.username:
        exists = await db.scalar(
            select(User.id).where(
                User.username == payload.email,
                User.id != user_id,
            )
        )
        if exists:
            raise AppException(
                400,
                "Email already in use",
                ErrorCode.USER_EMAIL_ALREADY_EXISTS,
            )

        values["username"] = payload.email

    # -------------------------------------------------
    # PASSWORD UPDATE
    # -------------------------------------------------
    if payload.password:
        values["password_hash"] = hash_password(payload.password)

    # -------------------------------------------------
    # ROLE UPDATE
    # -------------------------------------------------
    if payload.role and payload.role != user.role:
        if payload.role not in ALLOWED_ROLES:
            raise AppException(
                400,
                "Invalid role",
                ErrorCode.USER_ROLE_INVALID,
            )
        values["role"] = payload.role

    # -------------------------------------------------
    # ACTIVE STATUS UPDATE
    # -------------------------------------------------
    if payload.is_active is not None and payload.is_active != user.is_active:
        values["is_active"] = payload.is_active

    # -------------------------------------------------
    # NO-OP GUARD
    # -------------------------------------------------
    if not values:
        raise AppException(
            400,
            "No changes provided",
            ErrorCode.VALIDATION_ERROR,
        )

    # -------------------------------------------------
    # OPTIMISTIC UPDATE
    # -------------------------------------------------
    stmt = (
        update(User)
        .where(
            User.id == user_id,
            User.version == payload.version,
        )
        .values(
            **values,
            version=User.version + 1,
        )
        .returning(User)
    )

    result = await db.execute(stmt)
    updated_user = result.scalar_one_or_none()

    if not updated_user:
        raise AppException(
            409,
            "User was modified by another process",
            ErrorCode.USER_VERSION_CONFLICT,
        )

    # -------------------------------------------------
    # ACTIVITY LOGGING (BEFORE COMMIT)
    # -------------------------------------------------
    if "username" in values:
        await emit_activity(
            db=db,
            user_id=admin.id,
            username=admin.username,
            actor_role=admin.role.capitalize(),
            actor_email=admin.username,
            code=ActivityCode.UPDATE_USER_EMAIL,
            target_email=prev_email,
            new_email=updated_user.username,
        )

    if "password_hash" in values:
        await emit_activity(
            db=db,
            user_id=admin.id,
            username=admin.username,
            actor_role=admin.role.capitalize(),
            actor_email=admin.username,
            code=ActivityCode.UPDATE_USER_PASSWORD,
            target_email=updated_user.username,
        )

    if "role" in values:
        await emit_activity(
            db=db,
            user_id=admin.id,
            username=admin.username,
            actor_role=admin.role.capitalize(),
            actor_email=admin.username,
            code=ActivityCode.UPDATE_USER_ROLE,
            target_email=updated_user.username,
            old_role=prev_role,
            new_role=updated_user.role,
        )

    if "is_active" in values:
        activity_code = (
            ActivityCode.DEACTIVATE_USER
            if not updated_user.is_active
            else ActivityCode.REACTIVATE_USER
        )
        await emit_activity(
            db=db,
            user_id=admin.id,
            username=admin.username,
            actor_role=admin.role.capitalize(),
            actor_email=admin.username,
            code=activity_code,
            target_email=updated_user.username,
        )

    # -------------------------------------------------
    # COMMIT & RETURN
    # -------------------------------------------------
    await db.commit()
    return UserDetailSchema.from_orm(updated_user)

# =========================
# DEACTIVATE USER
# =========================
async def deactivate_user(
    db: AsyncSession,
    user_id: int,
    version: int,
    admin: User,
):
    logger.info(
        "Deactivating user",
        extra={
            "target_user_id": user_id,
            "requested_version": version,
            "actor_id": admin.id,
        },
    )

    stmt = (
        update(User)
        .where(
            User.id == user_id,
            User.version == version,
            User.is_active.is_(True),
        )
        .values(is_active=False, version=User.version + 1)
        .returning(User)
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(
            "User already inactive or version conflict",
            extra={"target_user_id": user_id},
        )
        raise AppException(
            409,
            "User already inactive",
            ErrorCode.CONFLICT,
        )

    await emit_activity(
        db,
        user_id=admin.id,
        username=admin.username,
        code=ActivityCode.DEACTIVATE_USER,
        actor_role=admin.role,
        actor_email=admin.username,
        target_email=user.username,
    )

    await db.commit()

    logger.info(
        "User deactivated successfully",
        extra={
            "target_user_id": user.id,
            "new_version": user.version,
        },
    )

    return UserDetailSchema.from_orm(user)


# =========================
# REACTIVATE USER
# =========================
async def reactivate_user(
    db: AsyncSession,
    user_id: int,
    version: int,
    admin: User,
):
    logger.info(
        "Reactivating user",
        extra={
            "target_user_id": user_id,
            "requested_version": version,
            "actor_id": admin.id,
        },
    )

    stmt = (
        update(User)
        .where(
            User.id == user_id,
            User.version == version,
            User.is_active.is_(False),
        )
        .values(is_active=True, version=User.version + 1)
        .returning(User)
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(
            "User already active or version conflict",
            extra={"target_user_id": user_id},
        )
        raise AppException(
            409,
            "User already active",
            ErrorCode.CONFLICT,
        )

    await emit_activity(
        db,
        user_id=admin.id,
        username=admin.username,
        code=ActivityCode.REACTIVATE_USER,
        actor_role=admin.role,
        actor_email=admin.username,
        target_email=user.username,
    )

    await db.commit()

    logger.info(
        "User reactivated successfully",
        extra={
            "target_user_id": user.id,
            "new_version": user.version,
        },
    )

    return UserDetailSchema.from_orm(user)


# =========================
# DASHBOARD
# =========================

async def get_user_dashboard_stats(db: AsyncSession):
    result = await db.execute(
        select(
            func.count(User.id).label("total_users"),
            func.count(User.id)
            .filter(User.is_active.is_(True))
            .label("active_users"),
            func.count(User.id)
            .filter(User.role == "admin")
            .label("admin_users"),
            func.count(User.id)
            .filter(User.is_online.is_(True))
            .label("online_users"),
        )
    )

    row = result.one()

    return UserDashboardStatsSchema(
        total_users=row.total_users,
        active_users=row.active_users,
        admin_users=row.admin_users,
        online_users=row.online_users,
    )
