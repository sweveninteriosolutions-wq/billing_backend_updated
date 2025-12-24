# app/services/masters/product_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, asc, desc, or_
from sqlalchemy.exc import IntegrityError

from app.models.masters.product_models import Product
from app.schemas.masters.product_schemas import (
    ProductCreate,
    ProductUpdate,
    ProductOut,
    ProductListData,
)
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode
from app.constants.activity_codes import ActivityCode
from app.utils.activity_helpers import emit_activity
from app.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_SORT_FIELDS = {
    "name": Product.name,
    "sku": Product.sku,
    "price": Product.price,
    "created_at": Product.created_at,
}


def _map_product(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        price=product.price,
        min_stock_threshold=product.min_stock_threshold,
        supplier_id=product.supplier_id,

        is_active=not product.is_deleted,
        version=product.version,

        created_by=product.created_by_id,
        updated_by=product.updated_by_id,
        created_by_name=product.created_by_username,
        updated_by_name=product.updated_by_username,

        created_at=product.created_at,
        updated_at=product.updated_at,
    )


# ---------------- CREATE ----------------
async def create_product(db: AsyncSession, payload: ProductCreate, user):
    exists = await db.scalar(
        select(Product.id).where(
            Product.sku == payload.sku,
            Product.is_deleted.is_(False),
        )
    )
    if exists:
        raise AppException(
            409,
            "SKU already exists",
            ErrorCode.PRODUCT_SKU_EXISTS,
        )

    product = Product(
        **payload.model_dump(),
        created_by_id=user.id,
        updated_by_id=user.id,
    )

    db.add(product)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        # Check if the name already exists to provide a more specific error.
        name_exists = await db.scalar(
                select(Product.id).where(Product.name == payload.name, Product.is_deleted.is_(False))
            )
        if name_exists:
            raise AppException(
                    409,
                    "Product name already exists",
                    ErrorCode.PRODUCT_NAME_EXISTS,
                )
            # If not name, assume it was a race condition on SKU.
        raise AppException(
                409,
                "SKU already exists",
                ErrorCode.PRODUCT_SKU_EXISTS,
            )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.CREATE_PRODUCT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=payload.name,
        sku=payload.sku,
    )

    await db.commit()
    await db.refresh(product)
    return _map_product(product)
from sqlalchemy import select, func, desc, asc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.masters.product_models import Product
from app.schemas.masters.product_schemas import ProductListData, ProductOut
from app.core.exceptions import AppException
from app.constants.error_codes import ErrorCode

ALLOWED_SORT_FIELDS = {
    "created_at": Product.created_at,
    "name": Product.name,
    "price": Product.price,
    "sku": Product.sku,
}


async def list_products(
    *,
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
    # =========================
    # BASE FILTERS
    # =========================
    filters = [Product.is_deleted.is_(False)]

    if search:
        filters.append(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%"),
            )
        )

    if category:
        filters.append(Product.category == category)

    if supplier_id:
        filters.append(Product.supplier_id == supplier_id)

    if min_price is not None:
        filters.append(Product.price >= min_price)

    if max_price is not None:
        filters.append(Product.price <= max_price)

    # =========================
    # SORTING
    # =========================
    sort_col = ALLOWED_SORT_FIELDS.get(sort_by)
    if not sort_col:
        raise AppException(
            400,
            "Invalid sort field",
            ErrorCode.VALIDATION_ERROR,
        )

    order_by = desc(sort_col) if order == "desc" else asc(sort_col)

    # =========================
    # DATA QUERY (FAST)
    # =========================
    data_stmt = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.category,
            Product.price,
            Product.min_stock_threshold,
            Product.supplier_id,
            Product.is_deleted,
            Product.version,
            Product.created_by_id,
            Product.updated_by_id,
            Product.created_at,
            Product.updated_at,
        )
        .where(*filters)
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = (await db.execute(data_stmt)).all()

    items = [
        ProductOut(
            id=r.id,
            sku=r.sku,
            name=r.name,
            category=r.category,
            price=r.price,
            min_stock_threshold=r.min_stock_threshold,
            supplier_id=r.supplier_id,
            is_active=not r.is_deleted,
            version=r.version,
            created_by=r.created_by_id,
            updated_by=r.updated_by_id,
            created_by_name=None,   # ❗ intentionally omitted
            updated_by_name=None,   # ❗ intentionally omitted
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]

    # =========================
    # COUNT QUERY (FAST)
    # =========================
    count_stmt = select(func.count()).select_from(
        select(Product.id).where(*filters).subquery()
    )

    total = await db.scalar(count_stmt)

    return ProductListData(
        total=total or 0,
        items=items,
    )



# ---------------- GET ----------------
async def get_product(db: AsyncSession, product_id: int):
    product = await db.get(Product, product_id)
    if not product or product.is_deleted:
        raise AppException(
            404,
            "Product not found",
            ErrorCode.PRODUCT_NOT_FOUND,
        )
    return _map_product(product)


# ---------------- UPDATE ----------------
async def update_product(
    db: AsyncSession,
    product_id: int,
    payload: ProductUpdate,
    user,
):
    current = await db.get(Product, product_id)
    if not current or current.is_deleted:
        raise AppException(
            404,
            "Product not found",
            ErrorCode.PRODUCT_NOT_FOUND,
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"version"})
    if not updates:
        raise AppException(
            400,
            "No changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    # -------------------------------------------------
    # UNIQUENESS CHECKS (SKU / NAME)
    # -------------------------------------------------
    if "sku" in updates and updates["sku"] != current.sku:
        exists = await db.scalar(
            select(Product.id).where(
                Product.sku == updates["sku"],
                Product.id != product_id,
                Product.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(
                409,
                "SKU already exists",
                ErrorCode.PRODUCT_SKU_EXISTS,
            )

    if "name" in updates and updates["name"] != current.name:
        exists = await db.scalar(
            select(Product.id).where(
                Product.name == updates["name"],
                Product.id != product_id,
                Product.is_deleted.is_(False),
            )
        )
        if exists:
            raise AppException(
                409,
                "Product name already exists",
                ErrorCode.PRODUCT_NAME_EXISTS,
            )

    # -------------------------------------------------
    # CHANGE TRACKING
    # -------------------------------------------------
    changes: list[str] = []
    for field, new_value in updates.items():
        old_value = getattr(current, field)
        if old_value != new_value:
            changes.append(f"{field}: {old_value} → {new_value}")

    if not changes:
        raise AppException(
            400,
            "No actual changes detected",
            ErrorCode.VALIDATION_ERROR,
        )

    # -------------------------------------------------
    # OPTIMISTIC UPDATE
    # -------------------------------------------------
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
            updated_by_id=user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise AppException(
            409,
            "Product was modified by another process",
            ErrorCode.PRODUCT_VERSION_CONFLICT,
        )

    # -------------------------------------------------
    # ACTIVITY LOG
    # -------------------------------------------------
    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.UPDATE_PRODUCT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=product.name,
        changes=", ".join(changes),
    )

    await db.commit()
    return _map_product(product)


# ---------------- DEACTIVATE ----------------
async def deactivate_product(db: AsyncSession, product_id: int, version: int, user):
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
            updated_by_id=user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise AppException(
            409,
            "Product was modified or already deactivated",
            ErrorCode.PRODUCT_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.DEACTIVATE_PRODUCT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=product.name,
    )

    await db.commit()
    return _map_product(product)


# ---------------- REACTIVATE ----------------
async def reactivate_product(db: AsyncSession, product_id: int, user):
    stmt = (
        update(Product)
        .where(
            Product.id == product_id,
            Product.is_deleted.is_(True),
        )
        .values(
            is_deleted=False,
            version=Product.version + 1,
            updated_by_id=user.id,
        )
        .returning(Product)
    )

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise AppException(
            409,
            "Product was modified or not deactivated",
            ErrorCode.PRODUCT_VERSION_CONFLICT,
        )

    await emit_activity(
        db=db,
        user_id=user.id,
        username=user.username,
        code=ActivityCode.REACTIVATE_PRODUCT,
        actor_role=user.role.capitalize(),
        actor_email=user.username,
        target_name=product.name,
    )

    await db.commit()
    return _map_product(product)
