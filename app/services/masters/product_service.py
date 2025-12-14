from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, asc, desc, update
from fastapi import HTTPException, status

from app.models.masters.product_models import Product
from app.schemas.masters.product_schemas import (
    ProductCreateSchema,
    ProductUpdateSchema,
    ProductTableSchema,
)
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity


ALLOWED_SORT_FIELDS = {
    "name": Product.name,
    "sku": Product.sku,
    "price": Product.price,
    "created_at": Product.created_at,
}


# =====================================================
# MAPPER
# =====================================================
def _map_product(product: Product) -> ProductTableSchema:
    return ProductTableSchema(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        price=product.price,
        min_stock_threshold=product.min_stock_threshold,
        supplier_id=product.supplier_id,

        is_active=not product.is_deleted,
        version=product.version,

        created_at=product.created_at,
        updated_at=product.updated_at,

        created_by_id=product.created_by_id,
        updated_by_id=product.updated_by_id,

        created_by_name=product.created_by_username,
        updated_by_name=product.updated_by_username,
    )


# =====================================================
# CREATE PRODUCT
# =====================================================
async def create_product(
    db: AsyncSession,
    payload: ProductCreateSchema,
    current_user,
):
    exists = await db.scalar(
        select(Product.id)
        .where(
            Product.sku == payload.sku,
            Product.is_deleted.is_(False),
        )
    )
    if exists:
        raise HTTPException(
            status_code=400,
            detail="SKU already exists",
        )

    product = Product(
        **payload.model_dump(),
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
    )

    db.add(product)

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.CREATE_PRODUCT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=payload.name,
        sku=payload.sku,
    )

    await db.commit()
    await db.refresh(product)

    return _map_product(product)


# =====================================================
# LIST PRODUCTS
# =====================================================
async def list_products(
    db: AsyncSession,
    search: str | None,
    category: str | None,
    supplier_id: int | None,
    min_price: float | None,
    max_price: float | None,
    page: int,
    page_size: int,
    sort_by: str,
    order: str,
):
    base = select(Product).where(Product.is_deleted.is_(False))

    if search:
        base = base.where(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%"),
            )
        )

    if category:
        base = base.where(Product.category == category)

    if supplier_id:
        base = base.where(Product.supplier_id == supplier_id)

    if min_price is not None:
        base = base.where(Product.price >= min_price)

    if max_price is not None:
        base = base.where(Product.price <= max_price)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Product.created_at)
    sort_expr = desc(sort_column) if order.lower() == "desc" else asc(sort_column)

    result = await db.execute(
        base.order_by(sort_expr)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    products = result.scalars().all()

    return total, [_map_product(p) for p in products]


# =====================================================
# GET PRODUCT
# =====================================================
async def get_product(
    db: AsyncSession,
    product_id: int,
) -> ProductTableSchema:

    product = await db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_deleted.is_(False),
        )
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return _map_product(product)


# =====================================================
# UPDATE PRODUCT (OPTIMISTIC LOCK)
# =====================================================
async def update_product(
    db: AsyncSession,
    product_id: int,
    payload: ProductUpdateSchema,
    current_user,
):
    existing = await db.get(Product, product_id)
    if not existing or existing.is_deleted:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No changes provided",
        )

    changes: list[str] = []
    for field, new_value in updates.items():
        old_value = getattr(existing, field)
        if old_value != new_value:
            changes.append(f"{field}: {old_value} → {new_value}")

    if not changes:
        raise HTTPException(
            status_code=400,
            detail="No actual changes detected",
        )

    stmt = (
        update(Product)
        .where(
            Product.id == product_id,
            Product.version == payload.version,
            Product.is_deleted.is_(False),
        )
        .values(
            **updates,
            version=Product.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product was modified by another process",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.UPDATE_PRODUCT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=product.name,
        changes=", ".join(changes),
    )

    await db.commit()

    return _map_product(product)


# =====================================================
# DEACTIVATE PRODUCT
# =====================================================
async def deactivate_product(
    db: AsyncSession,
    product_id: int,
    version: int,
    current_user,
):
    stmt = (
        update(Product)
        .where(
            Product.id == product_id,
            Product.version == version,
            Product.is_deleted.is_(False),
        )
        .values(
            is_deleted=True,
            version=Product.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product was modified or already deleted",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.DEACTIVATE_PRODUCT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=product.name,
    )

    await db.commit()

    return _map_product(product)


# =====================================================
# REACTIVATE PRODUCT
# =====================================================
async def reactivate_product(
    db: AsyncSession,
    product_id: int,
    version: int,
    current_user,
):
    stmt = (
        update(Product)
        .where(
            Product.id == product_id,
            Product.version == version,
            Product.is_deleted.is_(True),
        )
        .values(
            is_deleted=False,
            version=Product.version + 1,
            updated_by_id=current_user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product was modified or not deleted",
        )

    await emit_activity(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        code=ActivityCode.REACTIVATE_PRODUCT,
        actor_role=current_user.role.capitalize(),
        actor_email=current_user.username,
        target_name=product.name,
    )

    await db.commit()

    return _map_product(product)
