from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.inventory.stock_transfer_schemas import (
    StockTransferCreateSchema,
    StockTransferResponse,
    StockTransferListResponse,
)
from app.services.inventory.stock_transfer_service import (
    create_stock_transfer,
    complete_stock_transfer,
    cancel_stock_transfer,
    get_stock_transfer,
    list_stock_transfers,
)
from app.models.enums.stock_transfer_status import TransferStatus
from app.utils.check_roles import require_role

router = APIRouter(prefix="/stock-transfers", tags=["Stock Transfers"])


# =====================================================
# CREATE TRANSFER (PENDING)
# =====================================================
@router.post("/", response_model=StockTransferResponse)
async def create_stock_transfer_api(
    payload: StockTransferCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    transfer = await create_stock_transfer(
        db=db,
        product_id=payload.product_id,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        current_user=current_user,
    )
    return {
        "message": "Stock transfer created",
        "data": transfer,
    }


# =====================================================
# COMPLETE / VERIFY TRANSFER (ATOMIC)
# =====================================================
@router.post("/{transfer_id}/complete", response_model=StockTransferResponse)
async def complete_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    transfer = await complete_stock_transfer(
        db=db,
        transfer_id=transfer_id,
        current_user=current_user,
    )
    return {
        "message": "Stock transfer completed successfully",
        "data": transfer,
    }


# =====================================================
# CANCEL TRANSFER
# =====================================================
@router.post("/{transfer_id}/cancel", response_model=StockTransferResponse)
async def cancel_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    transfer = await cancel_stock_transfer(
        db=db,
        transfer_id=transfer_id,
        current_user=current_user,
    )
    return {
        "message": "Stock transfer cancelled",
        "data": transfer,
    }


# =====================================================
# GET BY ID
# =====================================================
@router.get("/{transfer_id}", response_model=StockTransferResponse)
async def get_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    transfer = await get_stock_transfer(db, transfer_id)
    return {
        "message": "Stock transfer retrieved",
        "data": transfer,
    }


# =====================================================
# LIST TRANSFERS
# =====================================================
@router.get("/", response_model=StockTransferListResponse)
async def list_stock_transfers_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),

    # Filters
    product_id: int | None = Query(None),
    status: TransferStatus | None = Query(None),
    from_location_id: int | None = Query(None),
    to_location_id: int | None = Query(None),

    # Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    total, transfers = await list_stock_transfers(
        db=db,
        product_id=product_id,
        status=status,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        page=page,
        page_size=page_size,
    )
    return {
        "message": "Stock transfers retrieved",
        "total": total,
        "data": transfers,
    }
