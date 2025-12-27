from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.orm import registry

mapper_registry = registry()

@mapper_registry.mapped
class QuotationItemView:
    __tablename__ = "quotation_item_view"
    __table_args__ = {"info": {"is_view": True}}

    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer)

    product_id = Column(Integer)
    product_name = Column(String)
    hsn_code = Column(Integer)

    quantity = Column(Integer)
    unit_price = Column(Numeric)
    line_total = Column(Numeric)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    created_by_id = Column(Integer)
    created_by_name = Column(String)
