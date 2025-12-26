from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class GRNView(Base):
    __tablename__ = "grn_view"
    __table_args__ = {"info": {"is_view": True}}

    # -----------------------
    # Primary Identity
    # -----------------------
    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    status = Column(String, nullable=False)
    version = Column(Integer) 
    purchase_order = Column(String(100), nullable=True)
    bill_number = Column(String(100), nullable=True, index=True)

    # -----------------------
    # JSON Aggregates
    # -----------------------
    supplier = Column(JSONB, nullable=False)
    location = Column(JSONB, nullable=False)

    items = Column(JSONB)     # array of items
    summary = Column(JSONB)   # no_of_items, total_value
    audit = Column(JSONB)     # created_at, created_by, updated_at, updated_by
