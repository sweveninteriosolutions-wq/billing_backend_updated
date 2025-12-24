# app/models/views/stock_transfer_view.py

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.core.db import Base

class StockTransferView(Base):
    __tablename__ = "vw_stock_transfers"
    __table_args__ = {"info": {"is_view": True}}

    id = Column(Integer, primary_key=True)

    product = Column(JSONB)
    quantity = Column(Integer)

    from_location = Column(JSONB)
    to_location = Column(JSONB)

    status = Column(String)

    transferred_by = Column(String)
    completed_by = Column(String)

    transfer_date = Column(DateTime)
