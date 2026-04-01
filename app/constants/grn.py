# app/constants/grn.py

from enum import Enum

class GRNStatus(str, Enum):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"
