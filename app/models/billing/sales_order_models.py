# app/models/sales_order_models.py

from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Enum,
    Index,
    Numeric,
    CheckConstraint,
)
from decimal import Decimal
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.sales_order_status import SalesOrderStatus


class SalesOrder(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "sales_orders"

    id = Column(Integer, primary_key=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False, index=True)

    status = Column(Enum(SalesOrderStatus), nullable=False, default=SalesOrderStatus.draft)

    customer = relationship("Customer", back_populates="sales_orders", lazy="joined")
    quotation = relationship("Quotation", back_populates="sales_orders", lazy="joined")
    invoices = relationship("Invoice", back_populates="sales_order", lazy="selectin")
    items = relationship("SalesOrderItem", back_populates="sales_order", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index(
            "ix_sales_order_customer_status",
            "customer_id",
            "status"
        ),
    )

    def __repr__(self):
        return (
            f"<SalesOrder id={self.id} "
            f"customer_id={self.customer_id} "
            f"status={self.status}>"
        )



class SalesOrderItem(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "sales_order_items"

    id = Column(Integer, primary_key=True)

    sales_order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    ordered_quantity = Column(Integer, nullable=False)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    fulfilled_quantity = Column(Integer, nullable=False, default=0)

    unit_price = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    
    sales_order = relationship("SalesOrder", back_populates="items", lazy="joined")
    product = relationship("Product", lazy="joined")

    __table_args__ = (
        CheckConstraint("ordered_quantity > 0", name="ck_soi_ordered_qty"),
        CheckConstraint("reserved_quantity >= 0", name="ck_soi_reserved_qty"),
        CheckConstraint("fulfilled_quantity >= 0", name="ck_soi_fulfilled_qty"),
        Index("ix_so_item_sales_order_product", "sales_order_id", "product_id"),
    )

    def __repr__(self):
        return (
            f"<SalesOrderItem id={self.id} "
            f"product_id={self.product_id} "
            f"ordered={self.ordered_quantity} "
            f"reserved={self.reserved_quantity} "
            f"fulfilled={self.fulfilled_quantity}>"
        )
