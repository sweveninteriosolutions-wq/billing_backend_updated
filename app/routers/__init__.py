# app/routers/__init__.py

from .users.user_router import router as user_router

from .auth.auth_router import router as auth_router
from .auth.activity_router import router as activity_router

from .masters.customer_router import router as customer_router
from .masters.supplier_router import router as supplier_router
from .masters.product_router import router as product_router
from .masters.discount_router import router as discount_router


from .inventory.inventory_balance_router import router as inventory_balance_router
from .inventory.inventory_location_router import router as inventory_location_router    
from .inventory.inventory_movement_router import router as inventory_movement_router
from .inventory.grn_router import router as grn_router
from .inventory.stock_transfer_router import router as stock_transfer_router

from .billing.quotation_router import router as quotation_router
from .billing.invoice_router import router as invoice_router
from .billing.payment_router import router as payment_router
from .billing.loyaltyTokens_router import router as loyalty_token_router

from .support.complaint_router import router as complaint_router
from .support.file_upload_router import router as file_upload_router
from .inventory.purchase_order_router import router as purchase_order_router
from .inventory.warehouse_router import router as warehouse_router
from .reports.reports_router import router as reports_router


__all__ = [
"user_router",

"auth_router",
"activity_router",

"customer_router",
"supplier_router",
"product_router",
"discount_router",

"inventory_balance_router",
"inventory_location_router",
"inventory_movement_router",
"grn_router",
"stock_transfer_router",

"quotation_router",
"invoice_router",
"payment_router",
"loyalty_token_router",

"complaint_router",
"file_upload_router",
"purchase_order_router",
"warehouse_router",
"reports_router",
]
