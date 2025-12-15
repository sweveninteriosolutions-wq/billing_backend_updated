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
async def list_users(db: AsyncSession, filters: UserListFilters):
    stmt = select(User)

    if filters.search:
        stmt = stmt.where(User.username.ilike(f"%{filters.search}%"))
    if filters.role:
        stmt = stmt.where(User.role == filters.role)
    if filters.is_active is not None:
        stmt = stmt.where(User.is_active == filters.is_active)
    if filters.is_online is not None:
        stmt = stmt.where(User.is_online == filters.is_online)
    if filters.created_today:
        stmt = stmt.where(func.date(User.created_at) == date.today())
    if filters.created_by:
        stmt = stmt.where(User.created_by_admin_id == filters.created_by)

    sort_col = User.created_at if filters.sort_by == "created_at" else User.username
    sort_col = sort_col.desc() if filters.sort_order == "desc" else sort_col.asc()

    stmt = stmt.order_by(sort_col).limit(filters.limit).offset(filters.offset)

    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        UserListItemSchema(
            id=u.id,
            username=u.username,
            role=u.role,
            status="Active" if u.is_active else "Inactive",
            is_online=u.is_online,
            last_login=u.last_login,
        )
        for u in users
    ]


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
async def update_user(db: AsyncSession, user_id: int, payload: UserUpdateSchema, admin: User):
    user = await db.get(User, user_id)
    if not user:
        raise AppException(404, "User not found", ErrorCode.USER_NOT_FOUND)

    values = {}

    if payload.email and payload.email != user.username:
        values["username"] = payload.email
    if payload.password:
        values["password_hash"] = hash_password(payload.password)
    if payload.role:
        if payload.role not in ALLOWED_ROLES:
            raise AppException(400, "Invalid role", ErrorCode.USER_ROLE_INVALID)
        values["role"] = payload.role
    if payload.is_active is not None:
        values["is_active"] = payload.is_active

    if not values:
        raise AppException(400, "No changes provided", ErrorCode.VALIDATION_ERROR)

    stmt = (
        update(User)
        .where(User.id == user_id, User.version == payload.version)
        .values(**values, version=User.version + 1)
        .returning(User)
    )

    result = await db.execute(stmt)
    updated_user = result.scalar_one_or_none()

    if not updated_user:
        raise AppException(409, "Version conflict", ErrorCode.USER_VERSION_CONFLICT)

    await db.commit()
    return UserDetailSchema.from_orm(updated_user)


# =========================
# DEACTIVATE USER
# =========================
async def deactivate_user(db: AsyncSession, user_id: int, version: int, admin: User):
    stmt = (
        update(User)
        .where(User.id == user_id, User.version == version, User.is_active.is_(True))
        .values(is_active=False, version=User.version + 1)
        .returning(User)
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AppException(409, "User already inactive", ErrorCode.CONFLICT)

    await db.commit()
    return UserDetailSchema.from_orm(user)


# =========================
# REACTIVATE USER
# =========================
async def reactivate_user(db: AsyncSession, user_id: int, version: int, admin: User):
    stmt = (
        update(User)
        .where(User.id == user_id, User.version == version, User.is_active.is_(False))
        .values(is_active=True, version=User.version + 1)
        .returning(User)
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise AppException(409, "User already active", ErrorCode.CONFLICT)

    await db.commit()
    return UserDetailSchema.from_orm(user)


# =========================
# DASHBOARD
# =========================
# app/services/users/user_services.py

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
