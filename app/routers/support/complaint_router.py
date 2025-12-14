from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.schemas.support.complaint_schemas import (
    ComplaintCreate,
    ComplaintUpdate,
    ComplaintStatusUpdate,
    ComplaintResponse,
    ComplaintListResponse,
)
from app.services.support.complaint_service import (
    create_complaint,
    get_complaint,
    list_complaints,
    update_complaint,
    update_complaint_status,
    delete_complaint,
)
from app.models.support.complaint_models import ComplaintStatus

router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post("/", response_model=ComplaintResponse)
async def create_complaint_api(
    payload: ComplaintCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),
):
    return await create_complaint(db, payload, current_user)


@router.get("/", response_model=ComplaintListResponse)
async def list_complaints_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),

    customer_id: int | None = Query(None),
    invoice_id: int | None = Query(None),
    product_id: int | None = Query(None),
    status: ComplaintStatus | None = Query(None),
    priority: str | None = Query(None),
    search: str | None = Query(None),

    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await list_complaints(
        db=db,
        customer_id=customer_id,
        invoice_id=invoice_id,
        product_id=product_id,
        status=status,
        priority=priority,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint_api(
    complaint_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),
):
    return await get_complaint(db, complaint_id)


@router.patch("/{complaint_id}", response_model=ComplaintResponse)
async def update_complaint_api(
    complaint_id: int,
    payload: ComplaintUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),
):
    return await update_complaint(db, complaint_id, payload, current_user)


@router.patch("/{complaint_id}/status", response_model=ComplaintResponse)
async def update_complaint_status_api(
    complaint_id: int,
    payload: ComplaintStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),
):
    return await update_complaint_status(db, complaint_id, payload, current_user)


@router.delete("/{complaint_id}", response_model=ComplaintResponse)
async def delete_complaint_api(
    complaint_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "support"])),
):
    return await delete_complaint(db, complaint_id, current_user)
