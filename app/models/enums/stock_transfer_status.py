import enum

class InventoryLocation(str, enum.Enum):
    showroom = "showroom"
    warehouse = "warehouse"


class TransferStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"