import enum

class ComplaintStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class ComplaintPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"