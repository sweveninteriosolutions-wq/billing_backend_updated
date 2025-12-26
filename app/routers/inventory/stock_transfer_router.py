from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.models.enums.stock_transfer_status import TransferStatus

from app.schemas.inventory.stock_transfer_schemas import (
    StockTransferCreateSchema,
    StockTransferResponse,
    StockTransferViewListResponse,

)

from app.services.inventory.stock_transfer_service import (
    create_stock_transfer,
    complete_stock_transfer,
    cancel_stock_transfer,
    get_stock_transfer,
    list_stock_transfers_view,
)

router = APIRouter(prefix="/stock-transfers", tags=["Stock Transfers"])


@router.post("/", response_model=StockTransferResponse)
async def create_stock_transfer_api(
    payload: StockTransferCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    return {
        "message": "Stock transfer created",
        "data": await create_stock_transfer(db, payload, current_user),
    }


@router.post("/{transfer_id}/complete", response_model=StockTransferResponse)
async def complete_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    return {
        "message": "Stock transfer completed",
        "data": await complete_stock_transfer(db, transfer_id, current_user),
    }


@router.post("/{transfer_id}/cancel", response_model=StockTransferResponse)
async def cancel_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    return {
        "message": "Stock transfer cancelled",
        "data": await cancel_stock_transfer(db, transfer_id, current_user),
    }


@router.get("/{transfer_id}", response_model=StockTransferResponse)
async def get_stock_transfer_api(
    transfer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    return {
        "message": "Stock transfer fetched",
        "data": await get_stock_transfer(db, transfer_id),
    }


@router.get(
    "/",
    response_model=StockTransferViewListResponse
)
async def list_stock_transfers_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),

    status: TransferStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    total, data, summary = await list_stock_transfers_view(
        db=db,
        status=status,
        page=page,
        page_size=page_size,
    )


    return {
        "message": "Stock transfers fetched",
        "total": total,
        "summary": summary,
        "data": data,
    }

