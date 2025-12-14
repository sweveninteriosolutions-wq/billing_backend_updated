import enum

class TransferStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"