from enum import Enum

class InvoiceStatus(str, Enum):
    draft = "draft"
    verified = "verified"
    partially_paid = "partially_paid"
    paid = "paid"
    fulfilled = "fulfilled"
    cancelled = "cancelled"
