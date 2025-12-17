# app/routers/masters/product_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.masters.product_schemas import (
    ProductCreate,
    ProductUpdate,
    ProductOut,
    ProductListData,
    VersionPayload,
)
from app.services.masters.product_service import (
    create_product,
    list_products,
    get_product,
    update_product,
    deactivate_product,
    reactivate_product,
)
from app.utils.check_roles import require_role
from app.utils.response import APIResponse, success_response
from app.utils.logger import get_logger

router = APIRouter(prefix="/products", tags=["Products"])
logger = get_logger(__name__)


@router.post("/", response_model=APIResponse[ProductOut])
async def create_product_api(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    logger.info("Create product", extra={"sku": payload.sku})
    product = await create_product(db, payload, user)
    return success_response("Product created successfully", product)


@router.get("/", response_model=APIResponse[ProductListData])
async def list_products_api(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
    search: str | None = Query(None, description="Search by name or SKU"),
    category: str | None = Query(None),
    supplier_id: int | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    logger.info("List products", extra={"search": search})
    data = await list_products(
        db=db,
        search=search,
        category=category,
        supplier_id=supplier_id,
        min_price=min_price,
        max_price=max_price,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        order=order,
    )
    return success_response("Products fetched successfully", data)


@router.get("/{product_id}", response_model=APIResponse[ProductOut])
async def get_product_api(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    product = await get_product(db, product_id)
    return success_response("Product fetched successfully", product)


@router.patch("/{product_id}", response_model=APIResponse[ProductOut])
async def update_product_api(
    product_id: int,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory"])),
):
    product = await update_product(db, product_id, payload, user)
    return success_response("Product updated successfully", product)


@router.patch("/{product_id}/deactivate", response_model=APIResponse[ProductOut])
async def deactivate_product_api(
    product_id: int,
    payload: VersionPayload,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    product = await deactivate_product(db, product_id, payload.version, user)
    return success_response("Product deactivated successfully", product)


@router.patch("/{product_id}/activate", response_model=APIResponse[ProductOut])
async def reactivate_product_api(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin"])),
):
    product = await reactivate_product(db, product_id, user)
    return success_response("Product reactivated successfully", product)
