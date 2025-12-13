# app/models/enums/inventory_movement_type.py

from enum import Enum


class InventoryMovementType(str, Enum):
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    ADJUSTMENT = "ADJUSTMENT"
