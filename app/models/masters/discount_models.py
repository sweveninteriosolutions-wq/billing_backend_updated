from sqlalchemy import Column, Integer, String, Numeric, Date, Boolean, Index, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Discount(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=False, unique=True, index=True)
    discount_type = Column(String(20), nullable=False)  # percentage | flat
    discount_value = Column(Numeric(10, 2), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, nullable=False, default=0)
    note = Column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint("discount_type IN ('percentage', 'flat')", name="ck_discount_type"),
        CheckConstraint("used_count >= 0", name="ck_discount_used_count_non_negative"),
        CheckConstraint("usage_limit IS NULL OR used_count <= usage_limit", name="ck_discount_usage_limit"),
        CheckConstraint("end_date >= start_date", name="ck_discount_date_range"),
        Index("ix_discount_active", "is_active"),
        Index("ix_discount_date_range", "start_date", "end_date"),
    )

    def __repr__(self):
        return f"<Discount id={self.id} code={self.code} type={self.discount_type}>"
