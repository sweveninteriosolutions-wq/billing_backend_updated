from pydantic import BaseModel, Field
from typing import List, Optional
from decimal import Decimal
from datetime import datetime


# ==============================
# ITEM SCHEMAS
# ==============================
class GRNItemCreateSchema(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, description="Received quantity")
    unit_cost: Decimal = Field(ge=0, description="Cost per unit")


class GRNItemUpdateSchema(GRNItemCreateSchema):
    pass


class GRNItemOutSchema(BaseModel):
    product_id: int
    quantity: int
    unit_cost: Decimal

# ==============================
# GRN INPUT SCHEMAS
# ==============================
class GRNCreateSchema(BaseModel):
    supplier_id: int
    location_id: int
    purchase_order: Optional[str] = None
    bill_number: Optional[str] = None
    notes: Optional[str] = None
    items: List[GRNItemCreateSchema]


class GRNUpdateSchema(BaseModel):
    supplier_id: Optional[int] = None
    location_id: Optional[int] = None
    purchase_order: Optional[str] = None
    bill_number: Optional[str] = None
    notes: Optional[str] = None
    items: Optional[List[GRNItemUpdateSchema]] = None

    # optimistic locking
    version: int

# ==============================
# GRN OUTPUT SCHEMAS
# ==============================
class GRNOutSchema(BaseModel):
    id: int
    supplier_id: Optional[int]
    location_id: int

    purchase_order: Optional[str]
    bill_number: Optional[str]
    notes: Optional[str]

    status: str
    version: int

    created_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]
    created_by_name: Optional[str]
    updated_by_name: Optional[str]

    items: List[GRNItemOutSchema]

    class Config:
        from_attributes = True


from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime


# -----------------------------
# NESTED SCHEMAS
# -----------------------------
class SupplierSchema(BaseModel):
    id: int
    name: str


class LocationSchema(BaseModel):
    id: int
    name: str


class ProductSchema(BaseModel):
    id: int
    name: str
    sku: str


class GRNItemViewSchema(BaseModel):
    product: ProductSchema
    quantity: int
    unit_cost: Decimal
    total: Decimal


class GRNSummaryViewSchema(BaseModel):
    no_of_items: int
    total_value: Decimal


class GRNAuditViewSchema(BaseModel):
    created_at: datetime
    created_by: str
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


# -----------------------------
# MAIN VIEW SCHEMA
# -----------------------------
class GRNViewSchema(BaseModel):
    id: int
    code: str
    status: str
    purchase_order: str
    bill_number: str
    version: int

    supplier: SupplierSchema
    location: LocationSchema

    items: List[GRNItemViewSchema]
    summary: GRNSummaryViewSchema
    audit: GRNAuditViewSchema

    class Config:
        from_attributes = True


# -----------------------------
# LIST RESPONSE
# -----------------------------
class GRNListViewData(BaseModel):
    total: int
    items: List[GRNViewSchema]
