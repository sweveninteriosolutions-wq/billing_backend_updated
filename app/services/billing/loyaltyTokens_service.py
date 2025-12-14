from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import noload
from fastapi import HTTPException

from app.models.billing.loyaltyTokens_models import LoyaltyToken
from app.schemas.billing.loyaltyTokens_schemas import (
    LoyaltyTokenOut,
    LoyaltyTokenResponse,
    LoyaltyTokenListResponse,
)


# =====================================================
# MAPPER
# =====================================================
def _map_token(token: LoyaltyToken) -> LoyaltyTokenOut:
    return LoyaltyTokenOut.model_validate(token)


# =====================================================
# GET BY ID
# =====================================================
async def get_loyalty_token(
    db: AsyncSession,
    token_id: int,
) -> LoyaltyTokenResponse:

    result = await db.execute(
        select(LoyaltyToken)
        .options(noload("*"))
        .where(LoyaltyToken.id == token_id)
    )
    token = result.scalar_one_or_none()

    if not token:
        raise HTTPException(404, "Loyalty token not found")

    return LoyaltyTokenResponse(
        message="Loyalty token retrieved successfully",
        data=_map_token(token),
    )


# =====================================================
# LIST TOKENS (GLOBAL FILTERS)
# =====================================================
async def list_loyalty_tokens(
    db: AsyncSession,
    *,
    customer_id: int | None,
    invoice_id: int | None,
    min_tokens: int | None,
    max_tokens: int | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
) -> LoyaltyTokenListResponse:

    base_query = (
        select(LoyaltyToken)
        .options(noload("*"))  # 🔥 critical for performance
    )

    if customer_id:
        base_query = base_query.where(LoyaltyToken.customer_id == customer_id)

    if invoice_id:
        base_query = base_query.where(LoyaltyToken.invoice_id == invoice_id)

    if min_tokens is not None:
        base_query = base_query.where(LoyaltyToken.tokens >= min_tokens)

    if max_tokens is not None:
        base_query = base_query.where(LoyaltyToken.tokens <= max_tokens)

    # ---- COUNT (no ORDER BY) ----
    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )

    # ---- SORTING ----
    sort_map = {
        "created_at": LoyaltyToken.created_at,
        "tokens": LoyaltyToken.tokens,
    }
    sort_col = sort_map.get(sort_by, LoyaltyToken.created_at)

    query = base_query.order_by(
        asc(sort_col) if order.lower() == "asc" else desc(sort_col)
    )

    # ---- PAGINATION ----
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )

    tokens = result.scalars().all()

    return LoyaltyTokenListResponse(
        message="Loyalty tokens retrieved successfully",
        total=total or 0,
        data=[_map_token(t) for t in tokens],
    )
