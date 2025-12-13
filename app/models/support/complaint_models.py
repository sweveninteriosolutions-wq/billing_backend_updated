# app/models/complaint_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Enum,
    Index
)
from sqlalchemy.orm import relationship
import enum

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin
from app.models.enums.complaint_status import ComplaintStatus, ComplaintPriority


class Complaint(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=True, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)

    status = Column(Enum(ComplaintStatus), nullable=False, default=ComplaintStatus.open)
    priority = Column(Enum(ComplaintPriority), nullable=False, default=ComplaintPriority.medium)
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    customer = relationship("Customer", lazy="joined")
    invoice = relationship("Invoice", lazy="selectin")
    sales_order = relationship("SalesOrder", lazy="selectin")
    quotation = relationship("Quotation", lazy="selectin")
    product = relationship("Product", lazy="selectin")

    verified_by = relationship("User", foreign_keys=[verified_by_id], lazy="joined")

    __table_args__ = (
        Index("ix_complaint_customer_status", "customer_id", "status"),
    )

    def __repr__(self):
        return f"<Complaint id={self.id} status={self.status}>"
