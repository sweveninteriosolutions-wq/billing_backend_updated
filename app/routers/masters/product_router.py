# app/routers/masters/product_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.schemas.masters.product_schemas import (
    ProductCreateSchema,
    ProductUpdateSchema,
    ProductResponseSchema,
    ProductListResponseSchema,
)
from app.services.masters.product_service import (
    create_product,
    list_products,
    update_product,
    deactivate_product,
    reactivate_product,
    get_product,
)
from app.utils.check_roles import require_role

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/", response_model=ProductResponseSchema)
async def create_product_api(
    payload: ProductCreateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    product = await create_product(db, payload, current_user)
    return {"msg": "Product created successfully", "data": product}

@router.get("/", response_model=ProductListResponseSchema)
async def list_products_api(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),

    # Filters
    search: str | None = Query(None, description="Search by name or SKU"),
    category: str | None = Query(None),
    supplier_id: int | None = Query(None),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),

    # Pagination
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),

    # Sorting
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
):
    total, products = await list_products(
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
    return {
        "msg": "Products fetched",
        "total": total,
        "data": products,
    }

@router.get("/{product_id}", response_model=ProductResponseSchema)
async def get_product_api(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    product = await get_product(db, product_id)
    return {
        "msg": "Product fetched successfully",
        "data": product,
    }




@router.patch("/{product_id}", response_model=ProductResponseSchema)
async def update_product_api(
    product_id: int,
    payload: ProductUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "inventory"])),
):
    product = await update_product(db, product_id, payload, current_user)
    return {"msg": "Product updated successfully", "data": product}

# -----------------------
# DEACTIVATE PRODUCT
# -----------------------
@router.delete("/{product_id}", response_model=ProductResponseSchema)
async def deactivate_product_api(
    product_id: int,
    version: int = Query(..., description="Current product version"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    product = await deactivate_product(
        db,
        product_id=product_id,
        version=version,
        current_user=current_user,
    )
    return {"msg": "Product deactivated successfully", "data": product}


# -----------------------
# REACTIVATE PRODUCT
# -----------------------
@router.post("/{product_id}/activate", response_model=ProductResponseSchema)
async def reactivate_product_api(
    product_id: int,
    version: int = Query(..., description="Current product version"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    product = await reactivate_product(
        db,
        product_id=product_id,
        version=version,
        current_user=current_user,
    )
    return {"msg": "Product reactivated successfully", "data": product}