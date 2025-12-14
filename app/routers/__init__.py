# app/routers/__init__.py

from .users.user_router import router as user_router

from .auth.auth_router import router as auth_router
from .auth.activity_router import router as activity_router

from .masters.customer_router import router as customer_router
from .masters.supplier_router import router as supplier_router
from .masters.product_router import router as product_router

from .inventory.inventory_balance_router import router as inventory_balance_router
from .inventory.inventory_location_router import router as inventory_location_router    
from .inventory.grn_router import router as grn_router


__all__ = [
"user_router",

"auth_router",
"activity_router",

"customer_router",
"supplier_router",
"product_router",

"inventory_balance_router",
"inventory_location_router",
"grn_router",

]
