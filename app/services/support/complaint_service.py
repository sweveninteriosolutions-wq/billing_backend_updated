from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
from sqlalchemy.orm import noload
from fastapi import HTTPException, status

from app.models.support.complaint_models import Complaint, ComplaintStatus
from app.schemas.support.complaint_schemas import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintStatusUpdate,
    ComplaintResponse,
    ComplaintListResponse,
)
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity


# =====================================================
# HELPERS
# =====================================================

def _detect_changes(model, updates: dict) -> list[str]:
    changes: list[str] = []
    for field, new_value in updates.items():
        old_value = getattr(model, field)
        if old_value != new_value:
            changes.append(f"{field}: {old_value} → {new_value}")
    return changes


ALLOWED_STATUS_TRANSITIONS = {
    ComplaintStatus.OPEN: {ComplaintStatus.IN_PROGRESS, ComplaintStatus.CLOSED},
    ComplaintStatus.IN_PROGRESS: {ComplaintStatus.RESOLVED},
    ComplaintStatus.RESOLVED: {ComplaintStatus.CLOSED},
}


# =====================================================
# CREATE
# =====================================================
async def create_complaint(
    db: AsyncSession,
    payload: ComplaintCreate,
    current_user,
) -> ComplaintResponse:
    """
    Create complaint.
    Enforces:
    - One complaint per customer + invoice + product
    """

    conditions = [
        Complaint.customer_id == payload.customer_id,
        Complaint.invoice_id == payload.invoice_id,
        Complaint.is_deleted.is_(False),
    ]

    if payload.product_id:
        conditions.append(Complaint.product_id == payload.product_id)
    else:
        conditions.append(Complaint.product_id.is_(None))

    exists = await db.scalar(select(Complaint.id).where(*conditions))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complaint already exists for this invoice & product",
        )

    complaint = Complaint(
        **payload.model_dump(),
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )

    db.add(complaint)
    await db.flush()  # ensure complaint.id is available

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_COMPLAINT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_id=complaint.id,
        customer_id=complaint.customer_id,
    )

    await db.commit()
    await db.refresh(complaint)

    return ComplaintResponse(
        message="Complaint created successfully",
        data=complaint,
    )


# =====================================================
# GET BY ID
# =====================================================
async def get_complaint(
    db: AsyncSession,
    complaint_id: int,
) -> ComplaintResponse:

    result = await db.execute(
        select(Complaint)
        .options(noload("*"))
        .where(
            Complaint.id == complaint_id,
            Complaint.is_deleted.is_(False),
        )
    )
    complaint = result.scalar_one_or_none()

    if not complaint:
        raise HTTPException(404, "Complaint not found")

    return ComplaintResponse(
        message="Complaint retrieved successfully",
        data=complaint,
    )


# =====================================================
# LIST
# =====================================================
async def list_complaints(
    db: AsyncSession,
    *,
    customer_id: int | None,
    invoice_id: int | None,
    product_id: int | None,
    status: ComplaintStatus | None,
    priority,
    search: str | None,
    page: int,
    page_size: int,
) -> ComplaintListResponse:

    base = (
        select(Complaint)
        .options(noload("*"))
        .where(Complaint.is_deleted.is_(False))
    )

    if customer_id:
        base = base.where(Complaint.customer_id == customer_id)
    if invoice_id:
        base = base.where(Complaint.invoice_id == invoice_id)
    if product_id:
        base = base.where(Complaint.product_id == product_id)
    if status:
        base = base.where(Complaint.status == status)
    if priority:
        base = base.where(Complaint.priority == priority)
    if search:
        like = f"%{search}%"
        base = base.where(
            or_(
                Complaint.title.ilike(like),
                Complaint.description.ilike(like),
            )
        )

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    result = await db.execute(
        base.order_by(desc(Complaint.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return ComplaintListResponse(
        message="Complaints retrieved successfully",
        total=total or 0,
        data=result.scalars().all(),
    )


# =====================================================
# UPDATE CONTENT
# =====================================================
async def update_complaint(
    db: AsyncSession,
    complaint_id: int,
    payload: ComplaintUpdate,
    current_user,
) -> ComplaintResponse:

    complaint = await db.get(Complaint, complaint_id)
    if not complaint or complaint.is_deleted:
        raise HTTPException(404, "Complaint not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No changes provided")

    changes = _detect_changes(complaint, updates)
    if not changes:
        raise HTTPException(400, "No actual changes detected")

    for k, v in updates.items():
        setattr(complaint, k, v)

    complaint.updated_by_id = current_user.id

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_COMPLAINT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_id=complaint.id,
        changes=", ".join(changes),
    )

    await db.commit()
    await db.refresh(complaint)

    return ComplaintResponse(
        message="Complaint updated successfully",
        data=complaint,
    )


# =====================================================
# UPDATE STATUS
# =====================================================
async def update_complaint_status(
    db: AsyncSession,
    complaint_id: int,  
    payload: ComplaintStatusUpdate,
    current_user,
) -> ComplaintResponse:

    result = await db.execute(
        select(Complaint)
        .options(noload("*"))  # 🔥 CRITICAL FIX
        .where(
            Complaint.id == complaint_id,
            Complaint.is_deleted.is_(False),
        )
        .with_for_update()
    )
    complaint = result.scalar_one_or_none()

    if not complaint:
        raise HTTPException(404, "Complaint not found")

    allowed = ALLOWED_STATUS_TRANSITIONS.get(complaint.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change status from {complaint.status} to {payload.status}",
        )

    old_status = complaint.status
    complaint.status = payload.status

    if payload.status in {
        ComplaintStatus.RESOLVED,
        ComplaintStatus.CLOSED,
    }:
        complaint.verified_by_id = current_user.id

    complaint.updated_by_id = current_user.id

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_COMPLAINT_STATUS,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_id=complaint.id,
        old_status=old_status.value,
        new_status=payload.status.value,
    )

    await db.commit()
    await db.refresh(complaint)

    return ComplaintResponse(
        message="Complaint status updated successfully",
        data=complaint,
    )


# =====================================================
# DELETE (SOFT)
# =====================================================
async def delete_complaint(
    db: AsyncSession,
    complaint_id: int,
    current_user,
) -> ComplaintResponse:

    complaint = await db.get(Complaint, complaint_id)
    if not complaint or complaint.is_deleted:
        raise HTTPException(404, "Complaint not found")

    complaint.is_deleted = True
    complaint.updated_by_id = current_user.id

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DELETE_COMPLAINT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_id=complaint.id,
    )

    await db.commit()

    return ComplaintResponse(
        message="Complaint deleted successfully",
        data=complaint,
    )
