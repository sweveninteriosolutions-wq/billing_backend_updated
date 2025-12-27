from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    Boolean,
    Enum,
)
from sqlalchemy.orm import registry
from sqlalchemy.sql.sqltypes import Date
from app.models.enums.quotation_status import QuotationStatus

mapper_registry = registry()

@mapper_registry.mapped
class QuotationView:
    __tablename__ = "quotation_view"
    __table_args__ = {"info": {"is_view": True}}

    id = Column(Integer, primary_key=True)
    quotation_number = Column(String)

    customer_id = Column(Integer)
    customer_name = Column(String)

    status = Column(
        Enum(
            QuotationStatus,
            name="quotationstatus",   # MUST match DB enum
            native_enum=True
        )
    )

    valid_until = Column(Date)

    items_count = Column(Integer)

    subtotal_amount = Column(Numeric(14, 2))
    tax_amount = Column(Numeric(14, 2))
    total_amount = Column(Numeric(14, 2))

    is_inter_state = Column(Boolean)

    version = Column(Integer)
    is_deleted = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    created_by_id = Column(Integer)
    created_by_name = Column(String)

    updated_by_id = Column(Integer)
    updated_by_name = Column(String)

    def __repr__(self):
        return f"<QuotationView {self.quotation_number} status={self.status}>"
