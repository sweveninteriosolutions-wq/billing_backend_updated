# app/constants/grn.py

from enum import Enum

class GRNStatus(str, Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    CANCELLED = "cancelled"
