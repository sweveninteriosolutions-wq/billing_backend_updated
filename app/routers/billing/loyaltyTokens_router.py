# app/routers/billing/loyaltyTokens_router.py
# ERP-045 FIXED: Added redemption endpoint POST /loyalty-tokens/redeem
#                and balance endpoint GET /loyalty-tokens/balance/{customer_id}.
# ERP-038 NOTE:  Router file kept as loyaltyTokens_router.py to avoid breaking the
#                __init__.py import alias. Rename the import in a future cleanup sprint.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response, APIResponse

# ERP-045: Switched to the new loyalty_token_service which has redemption implemented.
from app.services.billing.loyalty_token_service import (
    get_loyalty_token,
    list_loyalty_tokens,
    redeem_loyalty_tokens,
    get_customer_token_balance,
)

from app.schemas.billing.loyaltyTokens_schemas import (
    LoyaltyTokenOut,
    LoyaltyTokenListData,
    LoyaltyTokenRedeemRequest,
    LoyaltyTokenRedeemResponse,
)

router = APIRouter(
    prefix="/loyalty-tokens",
    tags=["Loyalty Tokens"],
)


# =====================================================
# GET BY ID
# =====================================================
@router.get(
    "/{token_id}",
    response_model=APIResponse[LoyaltyTokenOut],
)
async def get_loyalty_token_api(
    token_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier", "manager"])),
):
    token = await get_loyalty_token(db, token_id)
    return success_response("Loyalty token retrieved successfully", token)


# =====================================================
# GET CUSTOMER BALANCE
# ERP-045: New endpoint — returns net token balance for a customer.
# =====================================================
@router.get(
    "/balance/{customer_id}",
    response_model=APIResponse[dict],
)
async def get_customer_balance_api(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier", "manager"])),
):
    balance = await get_customer_token_balance(db, customer_id)
    return success_response("Customer token balance retrieved", balance)


# =====================================================
# LIST TOKENS
# =====================================================
@router.get(
    "/",
    response_model=APIResponse[LoyaltyTokenListData],
)
async def list_loyalty_tokens_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier", "manager"])),
    customer_id: int | None = Query(None),
    invoice_id: int | None = Query(None),
    min_tokens: int | None = Query(None, ge=0),
    max_tokens: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    data = await list_loyalty_tokens(
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
    return success_response("Loyalty tokens retrieved successfully", data)


# =====================================================
# REDEEM TOKENS
# ERP-045: New endpoint — redeem tokens for a customer.
# =====================================================
@router.post(
    "/redeem",
    response_model=APIResponse[LoyaltyTokenRedeemResponse],
)
async def redeem_tokens_api(
    payload: LoyaltyTokenRedeemRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "cashier"])),
):
    result = await redeem_loyalty_tokens(db, payload, user)
    return success_response("Loyalty tokens redeemed successfully", result)
