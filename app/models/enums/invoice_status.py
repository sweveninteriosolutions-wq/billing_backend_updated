# app/models/enums/invoice_status.py
import enum

class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    issued = "issued"              # inventory deducted here
    partially_paid = "partially_paid"
    paid = "paid"
    cancelled = "cancelled"
