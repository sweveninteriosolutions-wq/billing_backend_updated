# app/models/enums/sales_order_status.py
import enum

class SalesOrderStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    reserved = "reserved"          # optional stock reservation
    converted_to_invoice = "converted_to_invoice"
    cancelled = "cancelled"
    completed = "completed"
