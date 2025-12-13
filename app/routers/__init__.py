# app/routers/__init__.py

from .users.user_router import router as user_router

from .auth.auth_router import router as auth_router
from .auth.activity_router import router as activity_router

from .masters.customer_router import router as customer_router
from .masters.supplier_router import router as supplier_router


__all__ = [
"user_router",
"auth_router",
"activity_router",
"customer_router",
"supplier_router",
]
