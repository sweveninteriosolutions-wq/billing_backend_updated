import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import noload

from app.models.billing.loyaltyTokens_models import LoyaltyToken
from app.schemas.billing.loyaltyTokens_schemas import (
    LoyaltyTokenOut,
    LoyaltyTokenListData,
)

from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode

logger = logging.getLogger(__name__)


# =====================================================
# MAPPER
# =====================================================
def _map_token(token: LoyaltyToken) -> LoyaltyTokenOut:
    return LoyaltyTokenOut.model_validate(token)


# =====================================================
# GET LOYALTY TOKEN BY ID
# =====================================================
async def get_loyalty_token(
    db: AsyncSession,
    token_id: int,
) -> LoyaltyTokenOut:
    logger.info("Get loyalty token", extra={"token_id": token_id})

    result = await db.execute(
        select(LoyaltyToken)
        .options(noload("*"))
        .where(
            LoyaltyToken.id == token_id,
        )
    )

    token = result.scalar_one_or_none()
    if not token:
        raise AppException(
            404,
            "Loyalty token not found",
            ErrorCode.LOYALTY_TOKEN_NOT_FOUND,
        )

    return _map_token(token)


# =====================================================
# LIST LOYALTY TOKENS
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
) -> LoyaltyTokenListData:
    logger.info(
        "List loyalty tokens",
        extra={
            "customer_id": customer_id,
            "invoice_id": invoice_id,
            "min_tokens": min_tokens,
            "max_tokens": max_tokens,
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "order": order,
        },
    )

    # -------------------------------
    # BASE QUERY
    # -------------------------------
    base_query = (
        select(LoyaltyToken)
        .options(noload("*"))
    )

    if customer_id:
        base_query = base_query.where(LoyaltyToken.customer_id == customer_id)

    if invoice_id:
        base_query = base_query.where(LoyaltyToken.invoice_id == invoice_id)

    if min_tokens is not None:
        base_query = base_query.where(LoyaltyToken.tokens >= min_tokens)

    if max_tokens is not None:
        base_query = base_query.where(LoyaltyToken.tokens <= max_tokens)

    # -------------------------------
    # COUNT (NO SORT)
    # -------------------------------
    total = await db.scalar(
        select(func.count()).select_from(base_query.subquery())
    )

    # -------------------------------
    # SORT + PAGINATION
    # -------------------------------
    sort_map = {
        "created_at": LoyaltyToken.created_at,
        "tokens": LoyaltyToken.tokens,
    }
    sort_col = sort_map.get(sort_by, LoyaltyToken.created_at)

    stmt = (
        base_query
        .order_by(asc(sort_col) if order == "asc" else desc(sort_col))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    tokens = result.scalars().all()

    return LoyaltyTokenListData(
        total=total or 0,
        items=[_map_token(t) for t in tokens],
    )
