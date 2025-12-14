from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from fastapi import HTTPException, status

from app.models.users.user_models import User
from app.schemas.users.user_schemas import (
    UserCreateSchema,
    UserUpdateSchema,
    UserTableSchema,
    UserDashboardStatsSchema,
)
from app.core.security import hash_password
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity


ALLOWED_ROLES = {"admin", "cashier", "sales", "inventory"}


# =========================
# INTERNAL MAPPER
# =========================
def _map_user(user: User) -> UserTableSchema:
    return UserTableSchema(
        id=user.id,
        name=user.username.split("@")[0],
        email=user.username,
        role=user.role.capitalize(),
        status="Active" if user.is_active else "Inactive",
        last_login=user.last_login,
        is_online=user.is_online,
        version=user.version,
    )


# =========================
# CREATE USER
# =========================
async def create_user(
    db: AsyncSession,
    payload: UserCreateSchema,
    admin_user: User,
):
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    exists = await db.scalar(
        select(User.id).where(User.username == payload.email)
    )
    if exists:
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(
        username=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        created_by_admin_id=admin_user.id,
    )

    db.add(user)

    # 🔔 activity BEFORE commit
    await emit_activity(
        db=db,
        user_id=admin_user.id,
        username=admin_user.username,
        code=ActivityCode.CREATE_USER,
        actor_role=admin_user.role.capitalize(),
        actor_email=admin_user.username,
        target_email=payload.email,
        target_role=payload.role.capitalize(),
    )

    await db.commit()
    await db.refresh(user)

    return _map_user(user)


# =========================
# LIST USERS
# =========================
async def list_users(db: AsyncSession):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    return [_map_user(u) for u in result.scalars().all()]


# =========================
# UPDATE USER (OPTIMISTIC)
# =========================
async def update_user(
    db: AsyncSession,
    user_id: int,
    payload: UserUpdateSchema,
    admin_user: User,
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prev_role = user.role
    prev_active = user.is_active
    prev_email = user.username

    values: dict = {}

    if payload.email and payload.email != user.username:
        exists = await db.scalar(
            select(User.id).where(
                User.username == payload.email,
                User.id != user_id,
            )
        )
        if exists:
            raise HTTPException(status_code=400, detail="Email already in use")
        values["username"] = payload.email

    if payload.password:
        values["password_hash"] = hash_password(payload.password)

    if payload.role:
        if payload.role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if payload.role != user.role:
            values["role"] = payload.role

    if payload.is_active is not None and payload.is_active != user.is_active:
        values["is_active"] = payload.is_active

    if not values:
        raise HTTPException(status_code=400, detail="No changes detected")

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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User was modified by another process",
        )

    # -----------------------------
    # ACTIVITY LOGS (BEFORE COMMIT)
    # -----------------------------
    if "username" in values:
        await emit_activity(
            db=db,
            user_id=admin_user.id,
            username=admin_user.username,
            code=ActivityCode.UPDATE_USER_EMAIL,
            actor_role=admin_user.role.capitalize(),
            actor_email=admin_user.username,
            target_email=prev_email,
            new_email=updated_user.username,
        )

    if "password_hash" in values:
        await emit_activity(
            db=db,
            user_id=admin_user.id,
            username=admin_user.username,
            code=ActivityCode.UPDATE_USER_PASSWORD,
            actor_role=admin_user.role.capitalize(),
            actor_email=admin_user.username,
            target_email=updated_user.username,
        )

    if "role" in values:
        await emit_activity(
            db=db,
            user_id=admin_user.id,
            username=admin_user.username,
            code=ActivityCode.UPDATE_USER_ROLE,
            actor_role=admin_user.role.capitalize(),
            actor_email=admin_user.username,
            target_email=updated_user.username,
            previous_role=prev_role.capitalize(),
            target_role=updated_user.role.capitalize(),
        )

    if prev_active and not updated_user.is_active:
        await emit_activity(
            db=db,
            user_id=admin_user.id,
            username=admin_user.username,
            code=ActivityCode.DEACTIVATE_USER,
            actor_role=admin_user.role.capitalize(),
            actor_email=admin_user.username,
            target_email=updated_user.username,
        )

    if not prev_active and updated_user.is_active:
        await emit_activity(
            db=db,
            user_id=admin_user.id,
            username=admin_user.username,
            code=ActivityCode.REACTIVATE_USER,
            actor_role=admin_user.role.capitalize(),
            actor_email=admin_user.username,
            target_email=updated_user.username,
        )

    # ✅ SINGLE COMMIT
    await db.commit()

    return _map_user(updated_user)


# =========================
# DASHBOARD
# =========================
async def get_user_dashboard_stats(db: AsyncSession):
    total = await db.scalar(select(func.count()).select_from(User))
    active = await db.scalar(
        select(func.count()).where(User.is_active.is_(True))
    )
    admins = await db.scalar(
        select(func.count()).where(User.role == "admin")
    )
    online = await db.scalar(
        select(func.count()).where(User.is_online.is_(True))
    )

    return UserDashboardStatsSchema(
        total_users=total or 0,
        active_users=active or 0,
        admin_users=admins or 0,
        online_users=online or 0,
    )
