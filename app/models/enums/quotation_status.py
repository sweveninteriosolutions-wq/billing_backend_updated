# app/models/enums/quotation_status.py
import enum

class QuotationStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    converted_to_sales = "converted_to_sales"
    converted_to_invoice = "converted_to_invoice"
    cancelled = "cancelled"
