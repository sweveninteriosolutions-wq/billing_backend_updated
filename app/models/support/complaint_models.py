from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.core.db import Base
from app.models.base.mixins import AuditMixin
from app.models.enums.complaint_status import ComplaintStatus, ComplaintPriority




class Complaint(Base, AuditMixin):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True)

    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)

    status = Column(
        SAEnum(ComplaintStatus),
        nullable=False,
        default=ComplaintStatus.OPEN,
        index=True,
    )

    priority = Column(
        SAEnum(ComplaintPriority),
        nullable=False,
        default=ComplaintPriority.MEDIUM,
    )

    verified_by_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    is_deleted = Column(Boolean, default=False, nullable=False)

    # ----------------------------------
    # RELATIONSHIPS (NO eager joins)
    # ----------------------------------
    customer = relationship("Customer")
    invoice = relationship("Invoice")
    product = relationship("Product")
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index(
            "ix_complaint_customer_invoice_product",
            "customer_id",
            "invoice_id",
            "product_id",
        ),
    )

    def __repr__(self):
        return f"<Complaint id={self.id} status={self.status}>"
