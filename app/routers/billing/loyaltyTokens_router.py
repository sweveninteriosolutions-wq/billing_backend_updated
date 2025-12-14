from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.billing.loyaltyTokens_schemas import (
    LoyaltyTokenResponse,
    LoyaltyTokenListResponse,
)
from app.services.billing.loyaltyTokens_service import (
    get_loyalty_token,
    list_loyalty_tokens,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/loyalty-tokens", tags=["Loyalty Tokens"])


# =====================================================
# GET BY ID
# =====================================================
@router.get("/{token_id}", response_model=LoyaltyTokenResponse)
async def get_loyalty_token_api(
    token_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "billing"])),
):
    return await get_loyalty_token(db, token_id)


# =====================================================
# LIST TOKENS (FILTERS + PAGINATION)
# =====================================================
@router.get("/", response_model=LoyaltyTokenListResponse)
async def list_loyalty_tokens_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "billing"])),

    # Filters
    customer_id: int | None = Query(None),
    invoice_id: int | None = Query(None),
    min_tokens: int | None = Query(None, ge=0),
    max_tokens: int | None = Query(None, ge=0),

    # Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    # Sorting
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    return await list_loyalty_tokens(
        db=db,
        customer_id=customer_id,
        invoice_id=invoice_id,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )
