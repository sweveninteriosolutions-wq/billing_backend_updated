from sqlalchemy import Column, Integer, String, Text, Index
from sqlalchemy.orm import relationship
from app.core.db import Base
from app.models.base.mixins import TimestampMixin, SoftDeleteMixin, AuditMixin


class Supplier(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    supplier_code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    contact_person = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(255), nullable=True, index=True)
    address = Column(Text, nullable=True)
    gstin = Column(String(15), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)

    grns = relationship("GRN", back_populates="supplier", lazy="selectin")
    products = relationship("Product", back_populates="supplier", lazy="selectin")

    def __repr__(self):
        return f"<Supplier id={self.id} code={self.supplier_code} name={self.name}>"
