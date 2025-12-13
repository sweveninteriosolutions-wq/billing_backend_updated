from sqlalchemy import Column, Integer, String, Text, Index
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Supplier(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)

    name = Column(String(255), nullable=False, unique=True)
    contact_person = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)

    version = Column(Integer, nullable=False, default=1)

    # grns = relationship("GRN", back_populates="supplier", lazy="selectin")
    products = relationship("Product", back_populates="supplier", lazy="selectin")

    __table_args__ = (
        Index("ix_supplier_name", "name"),
        Index("ix_supplier_phone", "phone"),
        Index("ix_supplier_email", "email"),
    )

    def __repr__(self):
        return f"<Supplier id={self.id} name={self.name}>"
