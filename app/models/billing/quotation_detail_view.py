from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Enum
from sqlalchemy.types import Date, JSON
from sqlalchemy.orm import registry
from app.models.enums.quotation_status import QuotationStatus

mapper_registry = registry()

@mapper_registry.mapped
class QuotationDetailView:
    __tablename__ = "quotation_detail_view"
    __table_args__ = {"info": {"is_view": True}}

    id = Column(Integer, primary_key=True)
    quotation_number = Column(String)

    # JSON CUSTOMER OBJECT
    customer = Column(JSON)

    status = Column(
        Enum(
            QuotationStatus,
            name="quotationstatus",
            native_enum=True,
        )
    )

    valid_until = Column(Date)

    # AMOUNTS
    subtotal_amount = Column(Numeric(14, 2))
    tax_amount = Column(Numeric(14, 2))
    total_amount = Column(Numeric(14, 2))

    # GST
    is_inter_state = Column(Boolean)

    cgst_rate = Column(Numeric(5, 2))
    sgst_rate = Column(Numeric(5, 2))
    igst_rate = Column(Numeric(5, 2))

    cgst_amount = Column(Numeric(14, 2))
    sgst_amount = Column(Numeric(14, 2))
    igst_amount = Column(Numeric(14, 2))

    # META
    description = Column(String)
    notes = Column(String)
    additional_data = Column(JSON)

    version = Column(Integer)
    item_signature = Column(String)

    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    created_by_name = Column(String)
    updated_by_name = Column(String)

    # JSON ITEMS ARRAY
    items = Column(JSON)
