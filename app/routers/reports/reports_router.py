# app/routers/reports/reports_router.py
"""
Sales and inventory reports endpoints.

PERF-P1-6 FIXED: Replaced func.date(Invoice.created_at) >= date_val with
timezone-aware datetime range comparisons. Using func.date() wraps the column
in a function call which prevents the query planner from using the btree index
on created_at, causing full table scans. Range comparisons (col >= X AND col <= Y)
are sargable and allow index usage.
"""
import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.core.db import get_db
from app.utils.check_roles import require_role
from app.utils.response import success_response

from app.models.billing.invoice_models import Invoice, InvoiceItem
from app.models.masters.customer_models import Customer
from app.models.masters.product_models import Product
from app.models.enums.invoice_status import InvoiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])


def _date_range(from_date: date, to_date: date) -> tuple:
    """
    PERF-P1-6: Convert date objects to UTC datetime range boundaries.
    Returns (start_dt, end_dt) as timezone-aware datetimes suitable for
    index-friendly range comparisons on created_at columns.
    """
    start_dt = datetime.combine(from_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(to_date, time.max).replace(tzinfo=timezone.utc)
    return start_dt, end_dt


@router.get("/sales/summary")
async def sales_summary(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "manager"])),
    from_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    to_date: date = Query(default_factory=lambda: date.today()),
):
    start_dt, end_dt = _date_range(from_date, to_date)
    result = await db.execute(
        select(
            func.count(Invoice.id).label("invoice_count"),
            func.coalesce(func.sum(Invoice.net_amount), Decimal("0")).label("total_revenue"),
            func.coalesce(func.sum(Invoice.total_paid), Decimal("0")).label("total_collected"),
            func.coalesce(func.sum(Invoice.balance_due), Decimal("0")).label("outstanding"),
            func.coalesce(func.sum(Invoice.tax_amount), Decimal("0")).label("total_tax"),
            func.coalesce(func.sum(Invoice.discount_amount), Decimal("0")).label("total_discounts"),
        )
        .where(
            Invoice.is_deleted.is_(False),
            Invoice.status.notin_([InvoiceStatus.cancelled, InvoiceStatus.draft]),
            Invoice.created_at >= start_dt,   # PERF-P1-6: index-friendly range
            Invoice.created_at <= end_dt,
        )
    )
    row = result.first()

    return success_response("Sales summary retrieved", {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "invoice_count": row.invoice_count,
        "total_revenue": str(row.total_revenue),
        "total_collected": str(row.total_collected),
        "outstanding": str(row.outstanding),
        "total_tax": str(row.total_tax),
        "total_discounts": str(row.total_discounts),
    })


@router.get("/sales/daily")
async def daily_sales(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "manager"])),
    days: int = Query(30, ge=1, le=365),
):
    from_date = date.today() - timedelta(days=days - 1)
    start_dt, _ = _date_range(from_date, date.today())
    # func.date() in GROUP BY and ORDER BY is fine (not in WHERE) — no index impact there.
    result = await db.execute(
        select(
            func.date(Invoice.created_at).label("day"),
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.net_amount), Decimal("0")).label("revenue"),
        )
        .where(
            Invoice.is_deleted.is_(False),
            Invoice.status.notin_([InvoiceStatus.cancelled, InvoiceStatus.draft]),
            Invoice.created_at >= start_dt,   # PERF-P1-6: index-friendly
        )
        .group_by(func.date(Invoice.created_at))
        .order_by(func.date(Invoice.created_at))
    )
    rows = result.all()
    return success_response("Daily sales retrieved", [
        {"day": str(r.day), "count": r.count, "revenue": str(r.revenue)}
        for r in rows
    ])


@router.get("/products/top")
async def top_products(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "manager", "inventory"])),
    limit: int = Query(10, ge=1, le=50),
    from_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    to_date: date = Query(default_factory=lambda: date.today()),
):
    start_dt, end_dt = _date_range(from_date, to_date)
    result = await db.execute(
        select(
            InvoiceItem.product_id,
            Product.name.label("product_name"),
            Product.sku,
            func.sum(InvoiceItem.quantity).label("total_qty"),
            func.sum(InvoiceItem.line_total).label("total_revenue"),
        )
        .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
        .join(Product, Product.id == InvoiceItem.product_id)
        .where(
            Invoice.is_deleted.is_(False),
            Invoice.status.notin_([InvoiceStatus.cancelled, InvoiceStatus.draft]),
            Invoice.created_at >= start_dt,   # PERF-P1-6: index-friendly
            Invoice.created_at <= end_dt,
        )
        .group_by(InvoiceItem.product_id, Product.name, Product.sku)
        .order_by(desc(func.sum(InvoiceItem.quantity)))
        .limit(limit)
    )
    rows = result.all()
    return success_response("Top products retrieved", [
        {
            "product_id": r.product_id,
            "product_name": r.product_name,
            "sku": r.sku,
            "total_qty": r.total_qty,
            "total_revenue": str(r.total_revenue),
        }
        for r in rows
    ])


@router.get("/customers/top")
async def top_customers(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "manager"])),
    limit: int = Query(10, ge=1, le=50),
    from_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    to_date: date = Query(default_factory=lambda: date.today()),
):
    start_dt, end_dt = _date_range(from_date, to_date)
    result = await db.execute(
        select(
            Invoice.customer_id,
            Customer.name.label("customer_name"),
            func.count(Invoice.id).label("invoice_count"),
            func.sum(Invoice.net_amount).label("total_spend"),
        )
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(
            Invoice.is_deleted.is_(False),
            Invoice.status.notin_([InvoiceStatus.cancelled, InvoiceStatus.draft]),
            Invoice.created_at >= start_dt,   # PERF-P1-6: index-friendly
            Invoice.created_at <= end_dt,
        )
        .group_by(Invoice.customer_id, Customer.name)
        .order_by(desc(func.sum(Invoice.net_amount)))
        .limit(limit)
    )
    rows = result.all()
    return success_response("Top customers retrieved", [
        {
            "customer_id": r.customer_id,
            "customer_name": r.customer_name,
            "invoice_count": r.invoice_count,
            "total_spend": str(r.total_spend),
        }
        for r in rows
    ])


@router.get("/inventory/low-stock")
async def low_stock(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role(["admin", "inventory", "manager"])),
):
    from app.models.inventory.inventory_balance_models import InventoryBalance

    result = await db.execute(
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.min_stock_threshold,
            func.coalesce(func.sum(InventoryBalance.quantity), 0).label("total_stock"),
        )
        .outerjoin(InventoryBalance, InventoryBalance.product_id == Product.id)
        .where(Product.is_deleted.is_(False))
        .group_by(Product.id, Product.sku, Product.name, Product.min_stock_threshold)
        .having(
            func.coalesce(func.sum(InventoryBalance.quantity), 0) <= Product.min_stock_threshold
        )
        .order_by(func.coalesce(func.sum(InventoryBalance.quantity), 0))
    )
    rows = result.all()
    return success_response("Low stock products retrieved", [
        {
            "product_id": r.id,
            "sku": r.sku,
            "name": r.name,
            "min_stock_threshold": r.min_stock_threshold,
            "total_stock": r.total_stock,
        }
        for r in rows
    ])
