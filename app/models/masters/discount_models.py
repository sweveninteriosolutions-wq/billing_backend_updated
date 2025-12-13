# app/models/discount_models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Date,
    Boolean,
    Index
)
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Discount(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True)

    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)

    discount_type = Column(String(20), nullable=False)  # percentage | flat
    discount_value = Column(Numeric(10, 2), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, nullable=False, default=0)

    note = Column(String(255), nullable=True)

    invoices = relationship("Invoice", back_populates="discount", lazy="selectin")

    __table_args__ = (
        Index("ix_discount_active", "is_active"),
    )

    def __repr__(self):
        return f"<Discount id={self.id} code={self.code}>"
